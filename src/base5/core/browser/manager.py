from zope import schema
from zope.component import adapts, getUtility, getMultiAdapter
from zope.interface import Interface, implements

from zope.publisher.interfaces.browser import IBrowserView
from zope.publisher.interfaces.browser import IDefaultBrowserLayer

from plone.app.portlets.manager import ColumnPortletManagerRenderer
from plone.app.portlets.browser.manage import ManageContextualPortlets
from plone.app.portlets.browser.interfaces import IManageContextualPortletsView
from plone.app.portlets.browser.editmanager import ContextualEditPortletManagerRenderer

from Products.CMFCore.utils import getToolByName

from Products.CMFPlone.interfaces.siteroot import IPloneSiteRoot
from plone.app.layout.navigation.interfaces import INavigationRoot

from Products.Five.browser import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile

from base5.core.browser.interfaces import IHomepagePortletManager
from base5.core.interfaces import IHomePage, IHomePageView
from base5.core.utils import pref_lang

from plone.portlets.interfaces import IPortletManager

from zope.annotation.interfaces import IAttributeAnnotatable
from zope.annotation.interfaces import IAnnotations
from plone.memoize.view import memoize_contextless
from Acquisition import aq_inner

SPAN_KEY = 'genweb.portlets.span.'


class GenwebPortletRenderer(ColumnPortletManagerRenderer):
    """
    A renderer for the Genweb portlets
    """
    adapts(Interface, IDefaultBrowserLayer, IBrowserView, IHomepagePortletManager)
    template = ViewPageTemplateFile('templates/renderer.pt')


class gwContextualEditPortletManagerRenderer(ContextualEditPortletManagerRenderer):
    """Render a portlet manager in edit mode for contextual portlets"""
    adapts(Interface, IDefaultBrowserLayer, IManageContextualPortletsView, IHomepagePortletManager)

    template = ViewPageTemplateFile('templates/edit-manager-contextual.pt')


class gwManageContextualPortlets(ManageContextualPortlets):
    """ Define our very own view for manage portlets """

    def getValue(self, manager):
        portletManager = getUtility(IPortletManager, name=manager)
        spanstorage = getMultiAdapter((self.context, portletManager), ISpanStorage)
        return spanstorage.span

    @memoize_contextless
    def getTitle(self):
        return self.context.title

    @memoize_contextless
    def paginaPrincipal(self):
        return IHomePage.providedBy(self.context)


class ISpanStorage(IAttributeAnnotatable):
    """Marker persistent used to store span number for portlet managers"""

    span = schema.TextLine(title=u"Number of spans for this portletManager.")


class SpanStorage(object):
    """Multiadapter that adapts any context and IPortletManager to provide ISpanStorage"""
    implements(ISpanStorage)
    adapts(Interface, IPortletManager)

    def __init__(self, context, manager):
        self.context = context
        self.manager = manager
        self.key_id = SPAN_KEY + manager.__name__

        annotations = IAnnotations(context)
        self._span = annotations.setdefault(self.key_id, '')

    def get_span(self):
        annotations = IAnnotations(self.context)
        self._span = annotations.setdefault(self.key_id, '')
        return self._span

    def set_span(self, value):
        annotations = IAnnotations(self.context)
        annotations.setdefault(self.key_id, value)
        annotations[self.key_id] = value

    span = property(get_span, set_span)


class setPortletHomeManagerSpan(BrowserView):
    """ View that stores the span number assigned to this portletManager for
        this context.
    """

    def getPortletContainer(self):
        context = aq_inner(self.context)
        container = context

        # Portlet container will be in the context,
        # Except in the portal root, when we look for an alternative
        if INavigationRoot.providedBy(self.context):
            pc = getToolByName(context, 'portal_catalog')
            # Add the use case of mixin types of IHomepages. The main ones of a
            # non PAM-enabled site and the possible inner ones.
            result = pc.searchResults(object_provides=IHomePage.__identifier__,
                                      portal_type='Document',
                                      Language=pref_lang())
            if result:
                # Return the object without forcing a getObject()
                container = getattr(context, result[0].id, context)
        return container

    def __call__(self):
        manager = self.request.form['manager']
        span = self.request.form['span']
        portlet_container = self.getPortletContainer()
        portletManager = getUtility(IPortletManager, manager)
        spanstorage = getMultiAdapter((portlet_container, portletManager), ISpanStorage)
        spanstorage.span = span
        self.request.RESPONSE.setStatus('200')
        self.request.RESPONSE.setHeader('Content-type', 'application/json')
        return '{"status": "Saved!"}'