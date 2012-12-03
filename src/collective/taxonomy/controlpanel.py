from plone.app.controlpanel.form import ControlPanelForm
from plone.app.form.widgets.multicheckboxwidget import MultiCheckBoxWidget \
    as BaseMultiCheckBoxWidget
from plone.namedfile.field import NamedBlobFile
from plone.i18n.normalizer.interfaces import IIDNormalizer
from plone.behavior.interfaces import IBehavior

from Products.CMFPlone.interfaces import IPloneSiteRoot
from Products.CMFDefault.formlib.schema import ProxyFieldProperty
from Products.CMFDefault.formlib.schema import SchemaAdapterBase
from Products.statusmessages.interfaces import IStatusMessage

from zope import schema
from zope.interface import Interface
from zope.formlib import form as formlib
from zope.interface import implements
from zope.component import adapts, getUtility
from zope.i18n.interfaces import ITranslationDomain
from zope.schema.interfaces import IVocabularyFactory

from z3c.form import form, field
from z3c.form.interfaces import HIDDEN_MODE

from .i18n import MessageFactory as _
from .interfaces import ITaxonomy
from .exportimport import TaxonomyImportExportAdapter


class ITaxonomySettings(Interface):
    """ Schema for controlpanel settings """

    taxonomies = schema.List(title=_(u"Taxonomies"),
                             value_type=schema.Choice(
                                 description=_(u"help_taxonomies",
                                               default=u"Select the taxnomies"
                                               "you desire to modify"),
                                 required=False,
                                 vocabulary='collective.taxonomy.taxonomies',
                             ),
                             default=[],)


class TaxonomySettingsControlPanelAdapter(SchemaAdapterBase):
    adapts(IPloneSiteRoot)
    implements(ITaxonomySettings)

    def __init__(self, context):
        super(TaxonomySettingsControlPanelAdapter, self).__init__(context)

    taxonomies = ProxyFieldProperty(ITaxonomySettings['taxonomies'])


class MultiCheckBoxWidget(BaseMultiCheckBoxWidget):

    def __init__(self, field, request):
        """Initialize the widget."""
        super(MultiCheckBoxWidget, self).__init__(field,
                                                  field.value_type.vocabulary,
                                                  request)


class TaxonomySettingsControlPanel(ControlPanelForm):
    form_fields = formlib.FormFields(ITaxonomySettings)
    form_fields['taxonomies'].custom_widget = MultiCheckBoxWidget

    label = _("Taxonomy settings")
    description = _("Taxonomy settings")
    form_name = _("Taxonomy settings")

    @formlib.action(_(u'label_add_taxonomy', default=u'Add taxonomy'),
                    name=u'add-taxonomy')
    def handle_add_taxonomy_action(self, action, data):
        self.context.REQUEST.RESPONSE.redirect(
            self.context.portal_url() + '/@@taxonomy-add'
        )

    @formlib.action(_(u'label_delete_taxonomy', default=u'Delete taxonomy'),
                    name=u'delete_taxonomy')
    def handle_delete_taxonomy_action(self, action, data):
        if len(data.get('taxonomies', [])) > 0:
            sm = self.context.getSiteManager()

            for item in data['taxonomies']:
                utility = sm.queryUtility(ITaxonomy, name=item)
                utility.unregisterBehavior()

                sm.unregisterUtility(utility, ITaxonomy, name=item)
                sm.unregisterUtility(utility, IVocabularyFactory, name=item)
                sm.unregisterUtility(utility, ITranslationDomain, name=item)

        IStatusMessage(self.context.REQUEST).addStatusMessage(
            _(u"Taxonomy deleted."), type="info")

        return self.context.REQUEST.RESPONSE.redirect(
            self.context.portal_url() + '/@@taxonomy-settings'
        )

    @formlib.action(_(u'label_export', default=u"Export"),
                    name=u'export')
    def handle_export_action(self, action, data):
        taxonomies = data.get('taxonomies', [])

        if len(taxonomies) > 0:
            adapter = TaxonomyImportExportAdapter(self.context)
            self.context.REQUEST.RESPONSE.setHeader('Content-type', 'text/xml')
            return adapter.exportDocument(taxonomies[0])

        return None


class ITaxonomyForm(Interface):
    # Regular fields

    field_title = schema.TextLine(title=_(u"Field title"),
                                  required=True)

    field_description = schema.TextLine(title=_(u"Field description"),
                                        required=False)

    import_file = NamedBlobFile(title=_(u"Upload VDEX xml file"),
                                description=_(u" "),
                                required=False)

    is_required = schema.Bool(title=_(u"Is required?"),
                              required=True)

    multi_select = schema.Bool(title=_(u"Multi-select field"),
                               required=True)

    write_permission = schema.Choice(title=_(u"Write permission"),
                                     required=False,
                                     vocabulary='collective.taxonomy.permissions')

    # Taxonomy hidden field
    taxonomy = schema.TextLine(title=_(u"Taxonomy"),
                                  required=True)


class TaxonomyAddForm(form.AddForm):
    fields = field.Fields(ITaxonomyForm)

    def updateWidgets(self):
        form.AddForm.updateWidgets(self)
        self.widgets['taxonomy'].mode = HIDDEN_MODE

    def create(self, data):
        return data

    def add(self, data):
        # XXX: Not totally sure that we only need to remove the dash (-) ?
        remove_chars = ['-']

        if 'import_file' not in data:
            raise ValueError("Import file is not in form")

        # Normalize
        normalizer = getUtility(IIDNormalizer)
        data['field_name'] = normalizer.normalize(data['field_title'])

        for char in remove_chars:
            data['field_name'] = data['field_name'].replace(char, '')

        # Read import file
        import_file = data['import_file'].data
        del data['import_file']

        # Import
        adapter = TaxonomyImportExportAdapter(self.context)
        taxonomy_name = adapter.importDocument(import_file)

        # Register behavior
        sm = self.context.getSiteManager()
        utility = sm.queryUtility(ITaxonomy,
                                  name=taxonomy_name)

        utility.registerBehavior(**data)

        IStatusMessage(self.context.REQUEST).addStatusMessage(
            _(u"Taxonomy imported."), type="info")

        return self.context.REQUEST.RESPONSE.redirect(
            self.context.portal_url() + '/@@taxonomy-settings'
        )

    def nextURL(self):
        return self.context.portal_url() + '/@@taxonomy-settings'


class TaxonomyEditForm(form.EditForm):
    fields = field.Fields(ITaxonomyForm)

    def updateWidgets(self):
        form.EditForm.updateWidgets(self)
        self.widgets['taxonomy'].mode = HIDDEN_MODE

    def getContent(self):
        return TaxonomyEditFormAdapter(self.context)


class TaxonomyEditFormAdapter(object):
    adapts(IPloneSiteRoot)
    implements(ITaxonomyForm)

    def __init__(self, context):
        if context.REQUEST.get('form.widgets.taxonomy') is None:
            return

        taxonomy = context.REQUEST.get('form.widgets.taxonomy')

        sm = context.getSiteManager()
        utility = sm.queryUtility(ITaxonomy,
                                  name=taxonomy)

        generated_name = utility.getGeneratedName()

        self.__dict__['taxonomy'] = context.REQUEST.get('taxonomy')
        self.__dict__['behavior'] = sm.queryUtility(IBehavior,
                                                    name=generated_name)

    def __getattr__(self, attr):
        if 'behavior' not in self.__dict__:
            return None

        if 'taxonomy' is attr:
            return self.__dict__['taxonomy']

        return getattr(self.__dict__['behavior'], attr)

    def __setattr__(self, attr, value):
        if 'taxonomy' is attr:
            return

        setattr(self.__dict__['behavior'], attr, value)
