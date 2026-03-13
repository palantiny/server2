"""
Palantiny 보안 모듈
partner_token 검증 및 유틸리티.
"""
from typing import Optional

# partner_token 검증: 현재는 DB에서 존재 여부만 확인.
# 실제 운영 시에는 JWT 서명 검증, 만료 시간 등 추가 가능.
# 여기서는 검증 로직의 헬퍼 함수만 정의.


def verify_partner_token_format(token: Optional[str]) -> bool:
    """
    partner_token 형식 검증 (기본값: 비어있지 않은 문자열).
    실제 검증은 DB 조회로 수행.
    """
    return token is not None and len(token.strip()) > 0
