from celery import shared_task

from .push import send_push_to_user


@shared_task
def send_push(user_id, title, body, url=''):
    return send_push_to_user(user_id, title, body, url)
