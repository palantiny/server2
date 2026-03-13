"""
Palantiny 헬퍼 함수
session_id 생성 등 공통 유틸리티.
"""
import time
from uuid import uuid4


def generate_session_id(user_id: str | None = None) -> str:
    """
    세션 ID 생성.
    user_id가 있으면 user_id_timestamp 형태로 생성 (디버깅 용이),
    없으면 uuid4 사용.
    """
    if user_id:
        return f"{user_id}_{int(time.time() * 1000)}"
    return str(uuid4())
