from dataclasses import dataclass


@dataclass(frozen=True)
class FloorGridChanged:
    """IndexGrid 테이블의 row가 floor 단위로 변경되었을 때 발행.

    발행 시점:
        - IndexGridWriter.bulk_create 커밋 직후
        - IndexGridWriter.delete_by_floor 커밋 직후

    페이로드:
        floor_id: 변경된 Floor의 PK 값 (Floor.id).
                  Floor 자체에는 floor_id 컬럼이 없고 id가 PK이지만,
                  FK를 가진 모델(FloorGrid, IndexGrid)에서는 `instance.floor_id`로 접근.
    """
    floor_id: int


@dataclass(frozen=True)
class FloorDimensionsChanged:
    """Floor.width/length 또는 FloorGrid.cell_size 변경 시 발행.

    핸들러는 이 이벤트를 받아 IndexGrid를 재생성해야 한다.

    페이로드:
        floor_id: 변경된 Floor의 PK 값 (Floor.id).
    """
    floor_id: int
