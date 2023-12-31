# Generated by Django 4.1.7 on 2023-04-22 05:11

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bot", "0003_userwarn_userwarn_bot_userwar_chat_id_539915_idx_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChatSettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "chat_id",
                    models.BigIntegerField(unique=True, verbose_name="Chat ID"),
                ),
                (
                    "warn_count",
                    models.IntegerField(
                        default=3, verbose_name="Warnings before action"
                    ),
                ),
                (
                    "warn_counter_period",
                    models.DurationField(
                        default=datetime.timedelta(days=3),
                        verbose_name="Time period for warning check",
                    ),
                ),
                (
                    "mute_period",
                    models.DurationField(
                        default=datetime.timedelta(days=1), verbose_name="Mute period"
                    ),
                ),
            ],
            options={
                "verbose_name": "Chat settings",
                "verbose_name_plural": "Chats settings",
            },
        ),
    ]
