from django.apps import AppConfig
from django.db.models.signals import post_migrate


class StoreConfig(AppConfig):
    """The shop owner's panel at /store/: orders, products, promotions, returns and the team."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'store'
    verbose_name = 'Store panel'

    def ready(self):
        from .roles import create_role_groups

        # Not limited to this app: it has no models (so gets no signal of its own), and the permissions
        # it needs belong to other apps. Re-running is cheap and keeps the roles in sync.
        post_migrate.connect(create_role_groups, dispatch_uid='store.create_role_groups')
