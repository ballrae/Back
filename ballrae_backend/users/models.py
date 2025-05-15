from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin

# ✅ 사용자 생성을 위한 매니저 클래스
class UserManager(BaseUserManager):
    def create_user(self, kakao_id, user_nickname=None, password=None, **extra_fields):
        if not kakao_id:
            raise ValueError('카카오 ID는 반드시 필요합니다.')
        user = self.model(kakao_id=kakao_id, user_nickname=user_nickname, **extra_fields)
        user.set_unusable_password()  # 카카오는 비번 없으니까!
        user.save()
        return user

    def create_superuser(self, kakao_id, password=None, **extra_fields):
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(kakao_id, user_nickname="admin", password=password, **extra_fields)

# ✅ 인증용 커스텀 User 모델
class User(AbstractBaseUser, PermissionsMixin):
    kakao_id = models.CharField(max_length=255, unique=True)
    user_nickname = models.CharField(max_length=255)
    team_id = models.CharField(max_length=10, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    is_active = models.BooleanField(default=True)

    objects = UserManager()

    USERNAME_FIELD = 'kakao_id'  # 로그인 식별자로 kakao_id 사용
    REQUIRED_FIELDS = []  # createsuperuser 할 때 추가로 입력받을 필드

    def __str__(self):
        return self.user_nickname