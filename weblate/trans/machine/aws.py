import boto3

from django.conf import settings
from weblate.trans.machine.base import MachineTranslation, MissingConfiguration

class AWSTranslation(MachineTranslation):
 '''Adds support for AWS machine translation'''
    name = 'AWS'
    max_score = 88

    def __init__(self):
        super(AWSTranslation,self).__init__()
        if settings.MT_AWS_KEY is None:
            raise MissingConfiguration('Amazon Web Services requires API key')

    def download_languages(self):
        return ('en','ar','zh', 'fr','de','pt','es')

    def download_translations(self, source, language, text):
        client = boto3.client('translate')

        response = client.translate_text(Text = text,Source = source, Target = language)
        return (response['TranslatedText'],self.max_score,self.name,text)
    
