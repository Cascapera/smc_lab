from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0004_add_indexes_mp_external_ref"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="payment",
            new_name="payments_pa_mp_paym_7ddb9a_idx",
            old_name="pay_pay_mp_payment_idx",
        ),
        migrations.RenameIndex(
            model_name="payment",
            new_name="payments_pa_externa_e30da4_idx",
            old_name="pay_pay_external_idx",
        ),
        migrations.RenameIndex(
            model_name="subscription",
            new_name="payments_su_mp_prea_e0bd10_idx",
            old_name="pay_sub_mp_preapp_idx",
        ),
        migrations.RenameIndex(
            model_name="subscription",
            new_name="payments_su_externa_4c756e_idx",
            old_name="pay_sub_external_idx",
        ),
    ]
