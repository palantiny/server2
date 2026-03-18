import asyncio
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.core.database import async_session_maker
from app.models import User
from app.repositories.chat_history_repository import MongoChatHistoryRepository

async def seed_mongo():
    # 1. User ID 가져오기 (기존 시드 데이터 사용자)
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.partner_token == "partner_demo_token_001"))
        user = result.scalar_one_or_none()
        
    if not user:
        print("❌ 사용자를 찾을 수 없습니다. seed_data.py를 먼저 실행해 주세요.")
        return

    user_id = str(user.user_id)
    # 128k 요약 기능 등 테스트를 위해 적절한 세션 ID 부여
    session_id = f"session_mock_{user_id[:8]}"
    
    # 2. MongoDB 레포지토리 초기화
    repo = MongoChatHistoryRepository()
    
    # 3. 가짜 대화 내역 (당귀 주문)
    history = [
        ("user", "안녕하세요, 저번 달에 주문했던 당귀 추가로 주문하고 싶어요."),
        ("assistant", "안녕하세요! 네, 당귀 주문을 도와드리겠습니다. 저번과 동일하게 특상품으로 준비해 드릴까요? 몇 kg이나 필요하신가요?"),
        ("user", "네, 똑같이 특상품으로 50kg 주문할게요. 재고 충분하죠?"),
        ("assistant", "잠시 재고를 확인해 보겠습니다... 🔄 (DB_SQL 라우팅)\n네, 현재 당귀 특상품 재고 100kg 이상 보유 중입니다. 50kg 주문 접수 도와드릴까요? 단가는 kg당 15,000원입니다."),
        ("user", "네, 주문 접수해주세요! 언제쯤 배송될까요?"),
        ("assistant", "주문 접수가 완료되었습니다! (가승인 번호: ORD-10293) 내일 오전 10시에 바로 출고되어 모레쯤 받아보실 수 있습니다. 감사합니다!")
    ]
    
    print(f"🚀 사용자({user_id})의 세션({session_id})에 대화 기록을 넣고 있습니다...")
    
    for role, content in history:
        await repo.save(session_id, user_id, role, content)
        # MongoDB에 저장될 때 순서가 뒤죽박죽되지 않도록(created_at기준) 0.1초 쉬어줍니다.
        await asyncio.sleep(0.1)
        
    print("✅ 당귀 주문 대화 기록이 MongoDB에 성공적으로 저장되었습니다!")

if __name__ == "__main__":
    asyncio.run(seed_mongo())