from celery import shared_task
import httpx
import time
import logging

logger = logging.getLogger(__name__)


def warm_up_model():
    try:
        logger.info("🟡 모델 warm-up 요청 시작")
        res = httpx.post("http://hate-filter-api:8001/filter", json={"text": "테스트"}, timeout=3)
        logger.info(f"🟢 모델 warm-up 성공: status={res.status_code}, response={res.json()}")
    except Exception as e:
        logger.warning(f"🔴 모델 warm-up 실패: {e}")


@shared_task
def filter_post_text_task(post_id: int, title: str, content: str):
    try:
        start_time = time.time()
        logger.info(f"[필터링 시작] post_id={post_id}")

        def fetch_filtered(text):
            res = httpx.post("http://hate-filter-api:8001/filter", json={"text": text}, timeout=2)
            return res.json().get("masked_text", text)

        filtered_title = fetch_filtered(title)
        filtered_content = fetch_filtered(content)

        from .models import Post
        Post.objects.filter(id=post_id).update(
            post_title=filtered_title,
            post_content=filtered_content
        )

        end_time = time.time()
        logger.info(f"[필터링 완료] post_id={post_id}, 걸린 시간={end_time - start_time:.2f}s")

    except Exception as e:
        logger.error(f"Celery 게시글 필터링 실패: {e}")


@shared_task
def filter_comment_text_task(comment_id: int, text: str):
    try:
        start_time = time.time()
        logger.info(f"[댓글 필터링 시작] comment_id={comment_id}")

        res = httpx.post("http://hate-filter-api:8001/filter", json={"text": text}, timeout=2)
        filtered = res.json().get("masked_text", text)

        from .models import Comment
        comment = Comment.objects.get(id=comment_id)
        comment.comment_content = filtered
        comment.save()

        end_time = time.time()
        logger.info(f"[댓글 필터링 완료] comment_id={comment_id}, 걸린 시간={end_time - start_time:.2f}s")

    except Exception as e:
        logger.error(f"Celery 댓글 필터링 실패: {e}")


# 🔥 워커 시작 시 모델 warm-up
warm_up_model()