from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('product', '0006_productiontask_color_part'),
    ]

    operations = [
        migrations.AlterField(
            model_name='productiontask',
            name='part',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='product.part',
                verbose_name='قطعه'
            ),
        ),
    ]
