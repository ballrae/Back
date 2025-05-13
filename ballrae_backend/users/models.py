from django.db import models

# erd 짜지면 명확히

class User(models.Model):
    user_id = models.CharField(max_length=255, unique=True)  # 카카오 id
    username = models.CharField(max_length=255)              # 카카오 nickname

    def __str__(self):
        return self.username