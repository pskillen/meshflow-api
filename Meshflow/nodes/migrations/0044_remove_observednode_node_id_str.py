# #294: node_id_str is computed per ADR-0001

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("nodes", "0043_observednode_node_id_str_nullable"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="observednode",
            name="node_id_str",
        ),
    ]
