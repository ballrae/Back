from django.db import models


class User(models.Model):
    user_id = models.CharField(max_length=255, unique=True)
    username = models.CharField(max_length=255)
    email = models.EmailField()

    def __str__(self):
        return self.username