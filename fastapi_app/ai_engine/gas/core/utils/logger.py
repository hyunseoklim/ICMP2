"""
logger — Python 표준 logging 설정 함수.

본 모듈은 본 과업의 모든 영역(common, gas, power, generator)이
*동일한 형식의 로그*를 출력하도록 공통 로거 생성 함수를 제공한다.

설계 원칙:
    - 외부 로깅 라이브러리 의존 없음 (Python 표준 logging만 사용)
    - 콘솔은 항상 출력, 파일은 선택 출력
    - 같은 logger를 여러 번 setup해도 핸들러 중복 추가 방지
    - 로그 디렉토리 자동 생성

출력 형식:
    2026-05-19 16:50:23 [INFO] common.modules.sliding_window:45 - 메시지

표준 사용 예:
    >>> from gas.core.utils import setup_logger
    >>> logger = setup_logger(__name__)
    >>> logger.info("모듈 초기화 완료")
    
    # 파일 출력 함께
    >>> logger = setup_logger(__name__, log_file="train.log")
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional


# 로그 출력 형식
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 기본 로그 디렉토리 (호출 시점의 작업 디렉토리 기준)
_DEFAULT_LOG_DIR = "logs"


def setup_logger(
    name: str,
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    log_dir: Optional[str] = None,
) -> logging.Logger:
    """모듈명 기반 logger를 생성하거나 가져온다.
    
    같은 name으로 여러 번 호출되어도 핸들러가 중복 추가되지 않는다.
    
    Args:
        name: 로거 이름. 일반적으로 호출 모듈의 __name__ 전달.
              예: "common.modules.sliding_window"
        level: 로그 레벨. logging.DEBUG/INFO/WARNING/ERROR/CRITICAL.
               기본값 INFO.
        log_file: 파일 출력 시 파일명 (확장자 .log 포함).
                  None이면 콘솔만 출력. 예: "train.log"
        log_dir: 로그 디렉토리 경로. None이면 "logs/" 사용.
                 디렉토리가 없으면 자동 생성.
    
    Returns:
        설정된 Logger 인스턴스.
    
    Examples:
        >>> # 콘솔 출력만
        >>> logger = setup_logger("my_module")
        >>> logger.info("정상 메시지")
        
        >>> # 콘솔 + logs/train.log 파일 출력
        >>> logger = setup_logger("my_module", log_file="train.log")
        
        >>> # 디버그 레벨 + 사용자 정의 디렉토리
        >>> import logging
        >>> logger = setup_logger("my_module", level=logging.DEBUG,
        ...                       log_file="debug.log", log_dir="/tmp/logs")
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 같은 로거에 핸들러가 이미 설정되어 있으면 추가하지 않음 (중복 방지)
    # 단, 로그 레벨은 갱신
    if logger.handlers:
        return logger

    # 부모 로거의 핸들러로 전파 방지 (중복 출력 방지)
    logger.propagate = False

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # 콘솔 핸들러 (항상 추가)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 파일 핸들러 (log_file이 지정된 경우만)
    if log_file is not None:
        dir_path = Path(log_dir) if log_dir else Path(_DEFAULT_LOG_DIR)
        dir_path.mkdir(parents=True, exist_ok=True)

        file_path = dir_path / log_file
        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """이미 설정된 logger를 가져온다.
    
    `setup_logger`로 이미 초기화된 로거를 단순히 조회할 때 사용.
    핸들러가 없으면 setup_logger와 동일하게 작동 (콘솔 출력만, INFO 레벨).
    
    Args:
        name: 로거 이름.
    
    Returns:
        Logger 인스턴스.
    
    Examples:
        >>> # 진입점 스크립트에서 setup_logger로 초기화
        >>> # 다른 모듈에서는 get_logger로 사용
        >>> logger = get_logger(__name__)
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger
