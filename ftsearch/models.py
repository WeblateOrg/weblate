"""
Code based on Django Full-text search
"""
from django.db import models
from lang.models import Language
from trans.models import Unit

class Word(models.Model):
    word = models.CharField(max_length=255, db_index=True)
    language = models.ForeignKey(Language, null = True, blank = True)

    def __unicode__(self):
        return "%s: %s" % (self.language.name, self.word)

    class Meta:
        unique_together = ('word', 'language')

class WordLocation(models.Model):
    word = models.ForeignKey(Word)
    location = models.PositiveIntegerField()
    unit = models.ForeignKey(Unit)

    def __unicode__(self):
        return "%s[%d] (%d)" % (self.word, self.location, self.unit.id)
