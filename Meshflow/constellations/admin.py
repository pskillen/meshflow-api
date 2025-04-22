from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.db import transaction
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from nodes.models import MeshtasticNode
from .models import Constellation, ConstellationUserMembership, NodeAPIKey, NodeAuth


class ConstellationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "created_by",
        "get_member_count",
        "get_admin_count",
        "get_node_count",
        "get_api_key_count",
    )
    list_filter = ("created_by",)
    search_fields = ("name", "description", "created_by__username", "created_by__email")
    ordering = ("name",)
    readonly_fields = ("created_by",)

    def get_member_count(self, obj):
        return obj.constellationusermembership_set.count()

    get_member_count.short_description = _("Members")
    get_member_count.admin_order_field = "constellationusermembership__count"

    def get_admin_count(self, obj):
        return obj.constellationusermembership_set.filter(role="admin").count()

    get_admin_count.short_description = _("Admins")

    def get_node_count(self, obj):
        return obj.nodes.count()

    get_node_count.short_description = _("Nodes")
    get_node_count.admin_order_field = "nodes__count"

    def get_api_key_count(self, obj):
        return obj.api_keys.count()

    get_api_key_count.short_description = _("API Keys")
    get_api_key_count.admin_order_field = "api_keys__count"

    def save_model(self, request, obj, form, change):
        if not change:  # Only set created_by on creation
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


class ConstellationUserMembershipAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "constellation",
        "role",
        "get_user_email",
        "get_constellation_creator",
    )
    list_filter = ("role", "constellation", "user")
    search_fields = ("user__username", "user__email", "constellation__name")
    ordering = ("constellation__name", "user__username")

    def get_user_email(self, obj):
        return obj.user.email

    get_user_email.short_description = _("User Email")
    get_user_email.admin_order_field = "user__email"

    def get_constellation_creator(self, obj):
        return obj.constellation.created_by.username

    get_constellation_creator.short_description = _("Constellation Creator")
    get_constellation_creator.admin_order_field = "constellation__created_by__username"


class CopyToClipboardWidget(forms.Widget):
    template_name = 'admin/constellations/copy_to_clipboard_widget.html'

    def __init__(self, attrs=None):
        super().__init__(attrs)
        if attrs is None:
            attrs = {}
        attrs['readonly'] = 'readonly'
        attrs['style'] = 'background-color: #f8f9fa; cursor: not-allowed;'
        self.attrs = attrs

    def render(self, name, value, attrs=None, renderer=None):
        if value is None:
            value = ''
        final_attrs = self.build_attrs(attrs, {'name': name})
        return mark_safe(f'''
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
        ''')


class NodeAPIKeyForm(forms.ModelForm):
    """Form for NodeAPIKey that handles node selection."""

    nodes = forms.ModelMultipleChoiceField(
        queryset=MeshtasticNode.objects.none(),  # Start with empty queryset
        required=False,
        widget=FilteredSelectMultiple(_("Nodes"), is_stacked=False),
        label=_("Authorized Nodes"),
        help_text=_(
            "Select the nodes that this API key can access. Only nodes from the selected constellation will be shown."
        ),
    )

    class Meta:
        model = NodeAPIKey
        fields = ['name', 'constellation', 'key', 'is_active']
        widgets = {
            'key': CopyToClipboardWidget(),
        }
        labels = {
            'name': _('Key Name'),
            'constellation': _('Constellation'),
            'key': _('API Key'),
            'is_active': _('Active'),
        }
        help_texts = {
            'name': _('A descriptive name for this API key'),
            'constellation': _('The constellation this key belongs to'),
            'key': _('The API key used for authentication'),
            'is_active': _('Whether this key is currently active'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Only show nodes field for existing keys with a constellation
        if not (self.instance and self.instance.pk and self.instance.constellation_id):
            self.fields.pop('nodes', None)
            return

        # Set up the nodes for existing keys
        constellation = self.instance.constellation
        self.fields['nodes'].queryset = constellation.nodes.all().order_by('short_name')
        self.fields['nodes'].initial = self.instance.node_links.values_list(
            'node', flat=True
        )

    def clean(self):
        cleaned_data = super().clean()
        constellation = cleaned_data.get('constellation')

        # If we have a constellation, validate that the selected nodes belong to it
        if constellation and 'nodes' in cleaned_data:
            selected_nodes = cleaned_data['nodes']
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
        if 'nodes' in self.cleaned_data:
            with transaction.atomic():
                instance.save()

                # Get current and new node sets
                current_nodes = set(instance.node_links.values_list('node', flat=True))
                new_nodes = set(self.cleaned_data['nodes'])

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


class NodeAPIKeyAdmin(admin.ModelAdmin):
    form = NodeAPIKeyForm
    list_display = (
        "name",
        "constellation",
        "owner",
        "key",
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


admin.site.register(Constellation, ConstellationAdmin)
admin.site.register(ConstellationUserMembership, ConstellationUserMembershipAdmin)
admin.site.register(NodeAPIKey, NodeAPIKeyAdmin)
