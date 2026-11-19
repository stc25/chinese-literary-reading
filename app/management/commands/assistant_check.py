from django.core.management.base import BaseCommand, CommandError

from app.assistant import steps
from app.assistant.client import ModelError, client_from_config
from app.assistant.views import SettingsConfig


class Command(BaseCommand):
    help = "Check the model settings with one short request: python manage.py assistant_check"

    def handle(self, *args, **options):
        cfg = SettingsConfig()
        client = client_from_config(cfg)
        self.stdout.write(f"Model {client.model} at {client.host}; API key {'set' if client.api_key else 'not set'}.")
        try:
            with client.deadline(float(cfg.get("ASSISTANT_STEP_DEADLINE", 90))):
                r = steps.translate(client, "學而時習之")
        except ModelError as e:
            raise CommandError(f"{e} (see the log lines above for the service's answer)")
        self.stdout.write(f"OK: answered in {r.usage.seconds:.1f} s ({r.usage.prompt_tokens + r.usage.output_tokens} tokens): "
                          f"{r.data['translation'][:80]}")
