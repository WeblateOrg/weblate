from django.db import models

# Create your models here.

class Project(models.Model):
    name = models.CharField(max_length = 100)
    slug = models.SlugField(db_index = True)
    web = models.URLField()
    mail = models.EmailField()
    instructions = models.URLField()
    gitrepo = models.CharField(max_length = 200)
