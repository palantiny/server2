import asyncio
from redis.asyncio import Redis

async def test_connection():
    try:
        # .env 파일과 동일한 기본 포트로 연결 시도
        redis = Redis.from_url("redis://localhost:6379/0")
        
        print("🔄 Redis 서버에 'PING' 전송 중...")
        response = await redis.ping()
        
        if response:
            print("✅ 연결 대성공! Redis가 'PONG'으로 응답했습니다!")
        else:
            print("❌ 응답을 받지 못했습니다.")
            
        await redis.close()
    except Exception as e:
        print(f"❌ 연결 실패: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())
