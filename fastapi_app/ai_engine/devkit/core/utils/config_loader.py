"""
config_loader — yaml 설정 파일을 dict로 변환하는 함수.

본 모듈은 config/ 디렉토리의 yaml 파일을 표준 방식으로 로드하여,
모든 모듈이 *같은 방식으로 결정값을 받도록* 통일한다.

설계 원칙:
    - 외부 의존: PyYAML만 사용
    - 절대 경로 우선, 상대 경로는 호출 디렉토리 기준
    - 명확한 에러 메시지 (파일 없음·파싱 실패 구분)
    - 캐싱 없음 (단순. 필요 시 후속 추가)

표준 사용 예:
    >>> from devkit.core.utils import load_config, load_module_config
    
    # 절대/상대 경로로 로드
    >>> cfg = load_config("config/common/z_score.yaml")
    >>> cfg["z_threshold"]
    3.0
    
    # 모듈명·영역으로 자동 경로 구성
    >>> cfg = load_module_config("z_score", "common")
    >>> # → "config/common/z_score.yaml" 로드
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

import yaml


# 본 모듈 파일 위치 기준으로 ai_engine 루트 디렉토리 추정
# common/utils/config_loader.py → ai_engine 루트는 2단계 위
_AI_ENGINE_ROOT = Path(__file__).resolve().parent.parent.parent

# 기본 설정 디렉토리
_DEFAULT_CONFIG_DIR = _AI_ENGINE_ROOT / "config"


def load_config(config_path: Union[str, Path]) -> dict:
    """yaml 파일을 dict로 변환하여 반환한다.
    
    Args:
        config_path: yaml 파일 경로. 절대 경로 또는 호출 디렉토리 기준 상대 경로.
    
    Returns:
        파싱된 dict. 빈 yaml 파일은 빈 dict로 반환.
    
    Raises:
        FileNotFoundError: 파일이 존재하지 않을 때.
        yaml.YAMLError: yaml 파싱 실패 시 (구문 오류 등).
        ValueError: yaml 파일이 dict가 아닌 다른 구조일 때.
    
    Examples:
        >>> cfg = load_config("config/common/z_score.yaml")
        >>> cfg["z_threshold"]
        3.0
        
        >>> # Path 객체도 가능
        >>> from pathlib import Path
        >>> cfg = load_config(Path("/abs/path/to/config.yaml"))
    """
    path = Path(config_path)

    if not path.exists():
        raise FileNotFoundError(
            f"설정 파일을 찾을 수 없음: {path.resolve()}"
        )

    if not path.is_file():
        raise FileNotFoundError(
            f"지정된 경로가 파일이 아님: {path.resolve()}"
        )

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise yaml.YAMLError(
            f"yaml 파싱 실패 [{path}]: {e}"
        )

    # 빈 yaml은 None을 반환하므로 빈 dict로 정규화
    if data is None:
        return {}

    if not isinstance(data, dict):
        raise ValueError(
            f"설정 파일의 최상위는 dict여야 함 [{path}]. "
            f"받은 타입: {type(data).__name__}"
        )

    return data


def load_module_config(module_name: str, area: str = "common") -> dict:
    """모듈명과 영역명으로 설정 파일을 자동 로드한다.
    
    config/{area}/{module_name}.yaml 경로의 파일을 로드.
    호출자가 *상세 경로를 알 필요 없이* 모듈명·영역명만으로 설정 접근 가능.
    
    Args:
        module_name: 모듈 이름 (yaml 파일명에서 .yaml 제외).
                     예: "z_score", "isolation_forest", "arima"
        area: 영역 이름. "common" / "gas" / "power" 중 하나.
              기본값 "common".
    
    Returns:
        파싱된 dict.
    
    Raises:
        ValueError: area가 허용된 값이 아닐 때.
        FileNotFoundError: 자동 구성된 경로의 파일이 없을 때.
    
    Examples:
        >>> # config/common/z_score.yaml 로드
        >>> cfg = load_module_config("z_score", "common")
        
        >>> # config/gas/isolation_forest.yaml 로드
        >>> cfg = load_module_config("isolation_forest", "gas")
        
        >>> # config/power/arima.yaml 로드
        >>> cfg = load_module_config("arima", "power")
    """
    allowed_areas = {"common", "gas", "power"}
    if area not in allowed_areas:
        raise ValueError(
            f"area는 {allowed_areas} 중 하나여야 함. 받은 값: {area!r}"
        )

    config_path = _DEFAULT_CONFIG_DIR / area / f"{module_name}.yaml"
    return load_config(config_path)


def get_config_dir() -> Path:
    """ai_engine의 기본 config 디렉토리 경로를 반환한다.
    
    호출자가 config 파일 위치를 직접 확인하거나
    여러 파일을 일괄 처리할 때 사용.
    
    Returns:
        Path 객체 — ai_engine/config/ 의 절대 경로.
    
    Examples:
        >>> config_dir = get_config_dir()
        >>> yaml_files = list(config_dir.glob("**/*.yaml"))
    """
    return _DEFAULT_CONFIG_DIR
