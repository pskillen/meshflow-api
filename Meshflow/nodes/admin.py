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
            f"""  # noqa: E501
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
                    button.innerHTML = (
                        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" '
                        'fill="currentColor" class="bi bi-check" viewBox="0 0 16 16">'
                        '<path d="M10.97 4.97a.75.75 0 0 1 1.07 1.05l-3.99 4.99a.75.75 0 0 1-1.08.02L4.324 '
                        '8.384a.75.75 0 1 1 1.06-1.06l2.094 2.093 3.473-4.425a.267.267 0 0 1 .02-.022z"/>'
                        '</svg>'
                    );
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
        self.fields["nodes"].initial = self.instance.node_links.values_list("node", flat=True)

    def clean(self):
        cleaned_data = super().clean()
        constellation = cleaned_data.get("constellation")

        # If we have a constellation, validate that the selected nodes belong to it
        if constellation and "nodes" in cleaned_data:
            selected_nodes = cleaned_data["nodes"]
            valid_nodes = constellation.nodes.all()
            for node in selected_nodes:
                if node not in valid_nodes:
                    raise forms.ValidationError(f"Node {node} does not belong to constellation {constellation}")

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


class NodeIdDatalistWidget(forms.TextInput):
    template_name = "admin/nodes/node_id_datalist_widget.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        # Add all ObservedNodes to the context for the datalist
        context["datalist"] = [
            {
                "node_id": node.node_id,
                "display": f"{node.long_name or node.short_name or node.node_id_str} ({node.node_id})",
            }
            for node in ObservedNode.objects.all()
        ]
        context["datalist_id"] = f"{name}_datalist"
        return context


class LatLongMapWidget(forms.MultiWidget):
    template_name = "admin/nodes/latlong_map_widget.html"

    def __init__(self, attrs=None):
        widgets = [
            forms.TextInput(attrs={"class": "lat-input", "step": "any"}),
            forms.TextInput(attrs={"class": "lng-input", "step": "any"}),
        ]
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if value and isinstance(value, (list, tuple)) and len(value) == 2:
            return value
        return [None, None]

    def format_output(self, rendered_widgets):
        return f"Lat: {rendered_widgets[0]}<br>Lng: {rendered_widgets[1]}"

    def value_from_datadict(self, data, files, name):
        lat = data.get(f"{name}_0")
        lng = data.get(f"{name}_1")
        return [lat, lng]


class LatLongFormField(forms.Field):
    widget = LatLongMapWidget

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("required", False)
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if not value or not isinstance(value, (list, tuple)) or len(value) != 2:
            return [None, None]
        try:
            lat = float(value[0]) if value[0] not in (None, "", "None") else None
            lng = float(value[1]) if value[1] not in (None, "", "None") else None
            return [lat, lng]
        except (TypeError, ValueError):
            return [None, None]

    def prepare_value(self, value):
        # This ensures the widget gets a list/tuple for decompress
        if value is None:
            return [None, None]
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return value
        return [None, None]


class ManagedNodeAdminForm(forms.ModelForm):
    node_id = forms.CharField(
        label="Node ID",
        widget=NodeIdDatalistWidget,
        help_text="Select from observed nodes or enter a new node ID.",
    )

    latlong = LatLongFormField(
        label="Default Location (lat/lng)",
        help_text="Set the default latitude and longitude by dragging the marker on the map.",
    )

    class Meta:
        model = ManagedNode
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        lat = self.instance.default_location_latitude
        lng = self.instance.default_location_longitude
        self.initial["latlong"] = [lat, lng]

    def clean(self):
        cleaned_data = super().clean()
        latlong = self.cleaned_data.get("latlong")
        if latlong:
            cleaned_data["default_location_latitude"] = latlong[0]
            cleaned_data["default_location_longitude"] = latlong[1]
        return cleaned_data

    def save(self, commit=True):
        self.instance.default_location_latitude = self.cleaned_data.get("default_location_latitude")
        self.instance.default_location_longitude = self.cleaned_data.get("default_location_longitude")
        return super().save(commit=commit)


@admin.register(ManagedNode)
class ManagedNodeAdmin(admin.ModelAdmin):
    form = ManagedNodeAdminForm
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
            "latlong",
            "channel_0",
            "channel_1",
            "channel_2",
            "channel_3",
            "channel_4",
            "channel_5",
            "channel_6",
            "channel_7",
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
        "claimed_by",
        "role",
    )
    list_filter = (
        "hw_model",
        "sw_version",
        "claimed_by",
        "role",
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
        "claimed_by__username",
    )
    readonly_fields = (
        "internal_id",
        "node_id",
        "node_id_str",
        "mac_addr",
        "public_key",
        "role",
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
            "claimed_by",
            "role",
        ]
        return fields


# NOTE: You need to create the template file for NodeIdDatalistWidget at:
#   Meshflow/nodes/templates/admin/nodes/node_id_datalist_widget.html
# If the directories do not exist, create them as well.
