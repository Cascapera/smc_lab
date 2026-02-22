from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0003_plan_length"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="payment",
            index=models.Index(fields=["mp_payment_id"], name="pay_pay_mp_payment_idx"),
        ),
        migrations.AddIndex(
            model_name="payment",
            index=models.Index(fields=["external_reference"], name="pay_pay_external_idx"),
        ),
        migrations.AddIndex(
            model_name="subscription",
            index=models.Index(fields=["mp_preapproval_id"], name="pay_sub_mp_preapp_idx"),
        ),
        migrations.AddIndex(
            model_name="subscription",
            index=models.Index(fields=["external_reference"], name="pay_sub_external_idx"),
        ),
    ]
