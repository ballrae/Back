from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from ballrae_backend.teams.models import Team

class UserManager(BaseUserManager):
    def create_user(self, kakao_id, user_nickname=None, password=None, **extra_fields):
        if not kakao_id:
            raise ValueError('카카오 ID는 반드시 필요합니다.')
        user = self.model(kakao_id=kakao_id, user_nickname=user_nickname, **extra_fields)
        user.set_unusable_password()
        user.save()
        return user

    def create_superuser(self, kakao_id, password=None, **extra_fields):
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(kakao_id, user_nickname="admin", password=password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    kakao_id = models.CharField(max_length=255, unique=True)
    user_nickname = models.CharField(max_length=255)
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True)  # ✅ ForeignKey 변경
    created_at = models.DateTimeField(auto_now_add=True)
    
    is_active = models.BooleanField(default=True)

    objects = UserManager()

    USERNAME_FIELD = 'kakao_id'
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.user_nickname