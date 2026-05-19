from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from common.mesh_node_helpers import meshtastic_hex_to_int, meshtastic_id_to_hex
from common.protocol import Protocol

from .models import ManagedNode, ManagedNodeStatus, NodeAPIKey, NodeAuth, NodeLatestStatus, ObservedNode


class ManagedNodeActiveFilter(admin.SimpleListFilter):
    title = _("Feeder status")
    parameter_name = "feeder_active"

    def lookups(self, request, model_admin):
        return (
            ("active", _("Active")),
            ("deleted", _("Soft-deleted")),
        )

    def queryset(self, request, queryset):
        if self.value() == "active":
            return queryset.filter(deleted_at__isnull=True)
        if self.value() == "deleted":
            return queryset.filter(deleted_at__isnull=False)
        return queryset


MANAGED_NODE_COMMON_FIELDS = (
    "protocol",
    "meshtastic_node_id",
    "name",
    "owner",
    "constellation",
    "allow_auto_traceroute",
    "latlong",
)
MANAGED_NODE_CHANNEL_FIELDS = tuple(f"channel_{i}" for i in range(8))


class ProtocolListFilter(admin.SimpleListFilter):
    """Filter rows by mesh protocol (Meshtastic / MeshCore)."""

    title = _("Protocol")
    parameter_name = "protocol"

    def lookups(self, request, model_admin):
        return Protocol.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(protocol=int(self.value()))
        return queryset


class MeshCoreObservedIdentityFilter(admin.SimpleListFilter):
    """MeshCore ObservedNode rows by identity completeness (ADR-0001)."""

    title = _("MeshCore identity")
    parameter_name = "mc_identity"

    def lookups(self, request, model_admin):
        return (
            ("full", _("Full pubkey")),
            ("prefix_stub", _("Prefix stub only")),
            ("no_identity", _("Missing pubkey and prefix")),
        )

    def queryset(self, request, queryset):
        mc = queryset.filter(protocol=Protocol.MESHCORE)
        if self.value() == "full":
            return mc.filter(mc_pubkey__isnull=False)
        if self.value() == "prefix_stub":
            return mc.filter(mc_pubkey__isnull=True, mc_pubkey_prefix__isnull=False)
        if self.value() == "no_identity":
            return mc.filter(mc_pubkey__isnull=True, mc_pubkey_prefix__isnull=True)
        return queryset


class ApiKeyLinkedProtocolFilter(admin.SimpleListFilter):
    """Node API keys that have at least one linked ManagedNode of a protocol."""

    title = _("Linked feeder protocol")
    parameter_name = "linked_protocol"

    def lookups(self, request, model_admin):
        return Protocol.choices

    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        protocol = int(self.value())
        return queryset.filter(
            node_links__node__protocol=protocol,
            node_links__node__deleted_at__isnull=True,
        ).distinct()


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
        return mark_safe(f"""  # noqa: E501
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
        """)


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
                "meshtastic_node_id": node.meshtastic_node_id,
                "display": (f"{node.long_name or node.short_name or node.node_id_str} ({node.meshtastic_node_id})"),
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
        except TypeError, ValueError:
            return [None, None]

    def prepare_value(self, value):
        # This ensures the widget gets a list/tuple for decompress
        if value is None:
            return [None, None]
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return value
        return [None, None]


class ManagedNodeAdminForm(forms.ModelForm):
    meshtastic_node_id = forms.CharField(
        label=_("Node ID"),
        widget=NodeIdDatalistWidget,
        help_text=_("Select from observed Meshtastic nodes or enter a decimal id or !hex8."),
    )

    latlong = LatLongFormField(
        label=_("Default Location (lat/lng)"),
        help_text=_("Set the default latitude and longitude by dragging the marker on the map."),
    )

    class Meta:
        model = ManagedNode
        fields = "__all__"

    def _submitted_protocol(self):
        if not self.instance._state.adding:
            return self.instance.protocol
        if self.data:
            try:
                return int(self.data.get("protocol", Protocol.MESHTASTIC))
            except TypeError, ValueError:
                pass
        return int(self.initial.get("protocol", Protocol.MESHTASTIC))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        lat = self.instance.default_location_latitude
        lng = self.instance.default_location_longitude
        self.initial["latlong"] = [lat, lng]

        self.fields["protocol"].help_text = _(
            "MeshCore feeders use protocol MeshCore and node id 0; Meshtastic feeders use Meshtastic."
        )

        if self._submitted_protocol() == Protocol.MESHCORE:
            initial = self.instance.meshtastic_node_id if not self.instance._state.adding else 0
            self.fields["meshtastic_node_id"] = forms.IntegerField(
                label=_("Node ID (placeholder)"),
                required=False,
                initial=initial,
                min_value=0,
                help_text=_(
                    "Use 0 for MeshCore feeders (not used on the wire). "
                    "Display id is mc:feeder:<internal id> after save."
                ),
            )
        elif not self.instance._state.adding and self.instance.protocol == Protocol.MESHTASTIC:
            self.fields["meshtastic_node_id"].initial = meshtastic_id_to_hex(self.instance.meshtastic_node_id)

    def _protocol_from_form(self):
        protocol = self.cleaned_data.get("protocol") if hasattr(self, "cleaned_data") else None
        if protocol is not None:
            return protocol
        if self.data:
            try:
                return int(self.data.get("protocol", Protocol.MESHTASTIC))
            except TypeError, ValueError:
                pass
        if not self.instance._state.adding:
            return self.instance.protocol
        return Protocol.MESHTASTIC

    def clean_meshtastic_node_id(self):
        raw = self.cleaned_data.get("meshtastic_node_id")
        protocol = self._protocol_from_form()

        if protocol == Protocol.MESHCORE:
            if raw in (None, ""):
                return 0
            try:
                return int(raw)
            except TypeError, ValueError:
                raise forms.ValidationError(_("Enter 0 for MeshCore feeders."))

        text = str(raw).strip() if raw is not None else ""
        if not text:
            raise forms.ValidationError(_("Node ID is required."))
        if text.startswith("!"):
            return meshtastic_hex_to_int(text)
        try:
            return int(text)
        except ValueError:
            raise forms.ValidationError(_("Enter a decimal node ID or !hex8."))

    def clean(self):
        cleaned_data = super().clean()
        latlong = cleaned_data.get("latlong")
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
        "protocol",
        "meshtastic_node_id",
        "display_id",
        "name",
        "owner",
        "constellation",
        "allow_auto_traceroute",
        "status_is_sending_data",
        "status_last_packet_ingested_at",
    )
    list_filter = (
        ProtocolListFilter,
        ("constellation__protocol", admin.ChoicesFieldListFilter),
        ManagedNodeActiveFilter,
        "owner",
        "constellation",
        "allow_auto_traceroute",
    )
    search_fields = (
        "meshtastic_node_id",
        "name",
        "owner__username",
        "owner__email",
    )

    @admin.display(description=_("Feeding (API)"), boolean=True)
    def status_is_sending_data(self, obj):
        try:
            return obj.status.is_sending_data
        except ObjectDoesNotExist:
            return None

    @admin.display(description=_("Last packet ingested (status)"))
    def status_last_packet_ingested_at(self, obj):
        try:
            status = obj.status
        except ObjectDoesNotExist:
            return "—"
        if status.last_packet_ingested_at is None:
            return "—"
        return status.last_packet_ingested_at

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("status")

    @admin.display(description=_("Display ID"))
    def display_id(self, obj):
        return obj.node_id_str

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.protocol == Protocol.MESHCORE:
            return ("display_id",)
        return ()

    def get_fieldsets(self, request, obj=None):
        common = (_("Feeder"), {"fields": MANAGED_NODE_COMMON_FIELDS})
        channels = (
            _("Meshtastic channels"),
            {
                "fields": MANAGED_NODE_CHANNEL_FIELDS,
                "classes": ("collapse",),
                "description": _("Not used for MeshCore feeders."),
            },
        )
        if obj and obj.protocol == Protocol.MESHCORE:
            return (common,)
        return (common, channels)


@admin.register(ManagedNodeStatus)
class ManagedNodeStatusAdmin(admin.ModelAdmin):
    list_display = (
        "node",
        "last_packet_ingested_at",
        "is_sending_data",
        "updated_at",
    )
    list_select_related = ("node", "node__owner", "node__constellation")
    list_filter = (
        "is_sending_data",
        ("node__protocol", admin.ChoicesFieldListFilter),
        "node__constellation",
    )
    search_fields = ("node__name", "node__meshtastic_node_id", "node__owner__username")
    readonly_fields = (
        "node",
        "last_packet_ingested_at",
        "is_sending_data",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


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
        ApiKeyLinkedProtocolFilter,
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


class NodeLatestStatusInline(admin.StackedInline):
    model = NodeLatestStatus
    can_delete = False
    max_num = 1
    readonly_fields = (
        "latitude",
        "longitude",
        "altitude",
        "heading",
        "location_source",
        "precision_bits",
        "ground_speed",
        "ground_track",
        "sats_in_view",
        "pdop",
        "position_reported_time",
        "battery_level",
        "voltage",
        "channel_utilization",
        "air_util_tx",
        "uptime_seconds",
        "metrics_reported_time",
        "inferred_max_hops",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ObservedNode)
class ObservedNodeAdmin(admin.ModelAdmin):
    inlines = [NodeLatestStatusInline]
    list_display = (
        "protocol",
        "short_name",
        "long_name",
        "meshtastic_node_id",
        "node_id_str",
        "mc_pubkey_prefix",
        "meshtastic_hw_model",
        "get_inferred_max_hops",
        "last_heard",
        "environment_exposure",
        "weather_use",
        "claimed_by",
        "meshtastic_role",
    )

    def get_inferred_max_hops(self, obj):
        return obj.latest_status.inferred_max_hops if obj.latest_status else None

    get_inferred_max_hops.short_description = "Inferred max hops"
    list_filter = (
        ProtocolListFilter,
        MeshCoreObservedIdentityFilter,
        "meshtastic_hw_model",
        "environment_exposure",
        "weather_use",
        "claimed_by",
        "meshtastic_role",
        ("last_heard", admin.EmptyFieldListFilter),
    )
    search_fields = (
        "short_name",
        "long_name",
        "meshtastic_node_id",
        "node_id_str",
        "mc_pubkey",
        "mc_pubkey_prefix",
        "mac_addr",
        "meshtastic_hw_model",
        "meshtastic_public_key",
        "claimed_by__username",
    )
    readonly_fields = (
        "internal_id",
        "protocol",
        "meshtastic_node_id",
        "node_id_str",
        "mac_addr",
        "meshtastic_public_key",
        "meshtastic_role",
        "last_heard",
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("claimed_by", "latest_status")

    def get_fields(self, request, obj=None):
        common = [
            "protocol",
            "meshtastic_node_id",
            "node_id_str",
            "long_name",
            "short_name",
            "last_heard",
            "environment_exposure",
            "weather_use",
            "claimed_by",
            "meshtastic_role",
        ]
        if obj and obj.protocol == Protocol.MESHCORE:
            return common + ["mc_pubkey", "mc_pubkey_prefix"]
        return common + [
            "mac_addr",
            "meshtastic_hw_model",
            "meshtastic_public_key",
        ]


# NOTE: You need to create the template file for NodeIdDatalistWidget at:
#   Meshflow/nodes/templates/admin/nodes/node_id_datalist_widget.html
# If the directories do not exist, create them as well.
