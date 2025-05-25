from django.db import models
from ballrae_backend.teams.models import Team
from ballrae_backend.users.models import User  # 사용자 모델

class Post(models.Model):
    # id 칼럼은 자동 생성 되어 있음
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='posts')  # 팀별 게시글 team_id
    user = models.ForeignKey(User, on_delete=models.CASCADE)  # 작성자 user_id
    is_pinned = models.BooleanField(default=False)  # 공지 TF
    post_title = models.CharField(max_length=30)
    post_content = models.TextField()
    post_created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.post_title