# Generated by Django 4.1.7 on 2023-08-29 07:37

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bot", "0004_chatsettings"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatadmins",
            name="can_add_admin",
            field=models.BooleanField(default=False, verbose_name="Can add admins"),
        ),
    ]
