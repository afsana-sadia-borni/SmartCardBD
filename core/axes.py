def get_login_username(request, credentials):
    """The account name for django-axes lockouts.

    django-allauth authenticates with an `email` credential, while the login form field is `login`,
    so check both (lower-cased, so 'A@x.com' and 'a@x.com' share one counter).
    """
    credentials = credentials or {}
    value = credentials.get('email') or credentials.get('username')
    if not value and request is not None:
        value = request.POST.get('login', '')
    return (value or '').strip().lower()
