from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.db import transaction
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from .models import ManagedNode, NodeAPIKey, NodeAuth, ObservedNode


class CopyToClipboardWidget(forms.Widget):
    template_name = "admin/nodes/copy_to_clipboard_widget.html"

    def __init__(self, attrs=None):
        super().__init__(attrs)
        if attrs is None:
            attrs = {}
        attrs["readonly"] = "readonly"
        attrs["style"] = "background-color: #f8f9fa; cursor: not-allowed;"
        self.attrs = attrs

    def render(self, name, value, attrs=None, renderer=None):
        if value is None:
            value = ""
        final_attrs = self.build_attrs(attrs, {"name": name})
        return mark_safe(
            f"""
            <div class="copy-to-clipboard-container">
                <input type="text" value="{value}" {forms.widgets.flatatt(final_attrs)} readonly />
                <button type="button" class="copy-button" onclick="copyToClipboard(this)">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-clipboard" viewBox="0 0 16 16">
                        <path d="M4 1.5H3a2 2 0 0 0-2 2V14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V3.5a2 2 0 0 0-2-2h-1v1h1a1 1 0 0 1 1 1V14a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1h1v-1z"/>
                        <path d="M9.5 1a.5.5 0 0 1 .5.5v1a.5.5 0 0 1-.5.5h-3a.5.5 0 0 1-.5-.5v-1a.5.5 0 0 1 .5-.5h3zm-3-1A1.5 1.5 0 0 0 5 1.5v1A1.5 1.5 0 0 0 6.5 4h3A1.5 1.5 0 0 0 11 2.5v-1A1.5 1.5 0 0 0 9.5 0h-3z"/>
                    </svg>
                </button>
            </div>
            <script>
                function copyToClipboard(button) {{
                    const input = button.previousElementSibling;
                    input.select();
                    document.execCommand('copy');

                    // Show feedback
                    const originalText = button.innerHTML;
                    button.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-check" viewBox="0 0 16 16"><path d="M10.97 4.97a.75.75 0 0 1 1.07 1.05l-3.99 4.99a.75.75 0 0 1-1.08.02L4.324 8.384a.75.75 0 1 1 1.06-1.06l2.094 2.093 3.473-4.425a.267.267 0 0 1 .02-.022z"/></svg>';
                    setTimeout(() => {{ button.innerHTML = originalText; }}, 2000);
                }}
            </script>
            <style>
                .copy-to-clipboard-container {{
                    display: flex;
                    align-items: center;
                    gap: 8px;
                }}
                .copy-to-clipboard-container input {{
                    flex: 1;
                }}
                .copy-to-clipboard-container input[readonly] {{
                    background-color: #f8f9fa;
                    cursor: not-allowed;
                }}
                .copy-button {{
                    background: none;
                    border: none;
                    padding: 4px;
                    cursor: pointer;
                    color: #666;
                }}
                .copy-button:hover {{
                    color: #000;
                }}
            </style>
        """
        )


class NodeAPIKeyForm(forms.ModelForm):
    """Form for NodeAPIKey that handles node selection."""

    nodes = forms.ModelMultipleChoiceField(
        queryset=ManagedNode.objects.none(),  # Start with empty queryset
        required=False,
        widget=FilteredSelectMultiple(_("Nodes"), is_stacked=False),
        label=_("Authorized Nodes"),
        help_text=_(
            "Select the nodes that this API key can access. Only nodes from the selected constellation will be shown."
        ),
    )

    class Meta:
        model = NodeAPIKey
        fields = ["name", "constellation", "owner", "is_active"]
        widgets = {
            "key": CopyToClipboardWidget(),
        }
        labels = {
            "name": _("Key Name"),
            "constellation": _("Constellation"),
            "owner": _("Owner"),
            "is_active": _("Active"),
        }
        help_texts = {
            "name": _("A descriptive name for this API key"),
            "constellation": _("The constellation this key belongs to"),
            "owner": _("The user who owns this API key"),
            "is_active": _("Whether this key is currently active"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Only show nodes field for existing keys with a constellation
        if not (self.instance and self.instance.pk and self.instance.constellation_id):
            self.fields.pop("nodes", None)
            return

        # Set up the nodes for existing keys
        constellation = self.instance.constellation
        self.fields["nodes"].queryset = constellation.nodes.all().order_by("name")
        self.fields["nodes"].initial = self.instance.node_links.values_list(
            "node", flat=True
        )

    def clean(self):
        cleaned_data = super().clean()
        constellation = cleaned_data.get("constellation")

        # If we have a constellation, validate that the selected nodes belong to it
        if constellation and "nodes" in cleaned_data:
            selected_nodes = cleaned_data["nodes"]
            valid_nodes = constellation.nodes.all()
            for node in selected_nodes:
                if node not in valid_nodes:
                    raise forms.ValidationError(
                        f"Node {node} does not belong to constellation {constellation}"
                    )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if not instance.key:
            # Generate a new key if one doesn't exist
            instance.key = NodeAPIKey.generate_key()

        # Always save the instance first if we have nodes to update
        if "nodes" in self.cleaned_data:
            with transaction.atomic():
                instance.save()

                # Get current and new node sets
                current_nodes = set(instance.node_links.values_list("node", flat=True))
                new_nodes = set(self.cleaned_data["nodes"])

                # Remove nodes that are no longer selected
                nodes_to_remove = current_nodes - new_nodes
                if nodes_to_remove:
                    instance.node_links.filter(node__in=nodes_to_remove).delete()

                # Add new nodes that weren't previously selected
                nodes_to_add = new_nodes - current_nodes
                for node in nodes_to_add:
                    NodeAuth.objects.create(api_key=instance, node=node)
        elif commit:
            instance.save()

        return instance


@admin.register(ManagedNode)
class ManagedNodeAdmin(admin.ModelAdmin):
    list_display = (
        "node_id",
        "node_id_str",
        "name",
        "owner",
        "constellation",
    )
    list_filter = (
        "owner",
        "constellation",
    )
    search_fields = (
        "node_id",
        "node_id_str",
        "name",
        "owner__username",
        "owner__email",
    )

    def get_fields(self, request, obj=None):
        fields = [
            "node_id",
            "name",
            "owner",
            "constellation",
        ]
        return fields


@admin.register(NodeAPIKey)
class NodeAPIKeyAdmin(admin.ModelAdmin):
    form = NodeAPIKeyForm
    list_display = (
        "name",
        "constellation",
        "owner",
        "created_at",
        "last_used",
        "is_active",
    )
    list_filter = (
        "constellation",
        "owner",
        "is_active",
    )
    search_fields = (
        "name",
        "key",
        "constellation__name",
        "owner__username",
        "owner__email",
    )
    readonly_fields = (
        "key",
        "created_at",
        "last_used",
    )

    def get_fields(self, request, obj=None):
        """Only show nodes field for existing objects."""
        fields = [
            "name",
            "constellation",
            "owner",
            "key",
            "is_active",
            "created_at",
            "last_used",
        ]
        if obj and obj.pk and obj.constellation_id:
            fields.insert(3, "nodes")  # Insert nodes after owner
        return fields

    def get_readonly_fields(self, request, obj=None):
        if obj:  # Editing an existing object
            return self.readonly_fields + ("constellation",)
        return self.readonly_fields


@admin.register(ObservedNode)
class ObservedNodeAdmin(admin.ModelAdmin):
    list_display = (
        "short_name",
        "long_name",
        "node_id",
        "node_id_str",
        "hw_model",
        "sw_version",
    )
    list_filter = (
        "hw_model",
        "sw_version",
    )
    search_fields = (
        "short_name",
        "long_name",
        "node_id",
        "node_id_str",
        "mac_addr",
        "hw_model",
        "sw_version",
        "public_key",
    )
    readonly_fields = (
        "internal_id",
        "node_id",
        "node_id_str",
        "mac_addr",
        "public_key",
    )

    def get_fields(self, request, obj=None):
        """Show all fields for observed nodes."""
        fields = [
            "node_id",
            "mac_addr",
            "long_name",
            "short_name",
            "hw_model",
            "sw_version",
            "public_key",
        ]
        return fields