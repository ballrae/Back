from celery import shared_task
import httpx
import time
import logging

logger = logging.getLogger(__name__)

HATE_API_URL = "http://hate-filter-api:8001/filter"

def fetch_filtered(text: str) -> str:
    try:
        res = httpx.post(HATE_API_URL, json={"text": text}, timeout=3)
        res.raise_for_status()
        return res.json().get("masked_text", text)
    except Exception as e:
        logger.warning(f"[필터링 실패] 예외 발생: {e}")
        return text

@shared_task
def filter_post_text_task(post_id: int, title: str, content: str):
    start_time = time.time()
    logger.info(f"[게시글 필터링 시작] post_id={post_id}")

    filtered_title = fetch_filtered(title)
    filtered_content = fetch_filtered(content)

    from .models import Post
    Post.objects.filter(id=post_id).update(
        post_title=filtered_title,
        post_content=filtered_content
    )

    elapsed = time.time() - start_time
    logger.info(f"[게시글 필터링 완료] post_id={post_id}, 걸린 시간={elapsed:.2f}s")

@shared_task
def filter_comment_text_task(comment_id: int, text: str):
    start_time = time.time()
    logger.info(f"[댓글 필터링 시작] comment_id={comment_id}")

    filtered = fetch_filtered(text)

    from .models import Comment
    Comment.objects.filter(id=comment_id).update(
        comment_content=filtered
    )

    elapsed = time.time() - start_time
    logger.info(f"[댓글 필터링 완료] comment_id={comment_id}, 걸린 시간={elapsed:.2f}s")