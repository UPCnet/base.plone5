import os
from five import grok
from zope.interface import Interface
from zope.interface import alsoProvides
from zope.component.hooks import getSite

from Products.CMFPlone.interfaces import IPloneSiteRoot
from Products.CMFCore.utils import getToolByName
from Products.PluggableAuthService.interfaces.plugins import IUserAdderPlugin, IPropertiesPlugin
from Products.PlonePAS.interfaces.group import IGroupManagement

from base5.core.utils import add_user_to_catalog
from base5.core.utils import reset_user_catalog
from base5.core.utils import json_response

from plone import api
from souper.soup import get_soup

import pkg_resources
import logging

try:
    pkg_resources.get_distribution('Products.PloneLDAP')
except pkg_resources.DistributionNotFound:
    HAS_LDAP = False
else:
    HAS_LDAP = True
    from Products.PloneLDAP.factory import manage_addPloneLDAPMultiPlugin
    from Products.LDAPUserFolder.LDAPUserFolder import LDAPUserFolder

try:
    pkg_resources.get_distribution('plone.app.contenttypes')
except pkg_resources.DistributionNotFound:
    HAS_DXCT = False
else:
    HAS_DXCT = True
    from plone.dexterity.utils import createContentInContainer

logger = logging.getLogger(__name__)

LDAP_PASSWORD = os.environ.get('ldapbindpasswd', '')


class setupDX(grok.View):
    """ Setup View that fixes p.a.ct front-page
    """
    grok.name('setupdxctsite')
    grok.context(Interface)
    grok.require('cmf.ManagePortal')

    def render(self):
        try:
            from plone.protect.interfaces import IDisableCSRFProtection
            alsoProvides(self.request, IDisableCSRFProtection)
        except:
            pass
        if HAS_DXCT:
            portal = getSite()
            pl = getToolByName(portal, 'portal_languages')
            if getattr(portal, 'front-page', False):
                portal.manage_delObjects('front-page')
                frontpage = createContentInContainer(portal, 'Document', title=u"front-page", checkConstraints=False)
                frontpage.exclude_from_nav = True
                frontpage.language = pl.getDefaultLanguage()
                frontpage.reindexObject()
            # Set the default page to the homepage view
            portal.setDefaultPage('homepage')
            return self.request.response.redirect(portal.absolute_url())
        else:
            return 'This site has no p.a.contenttypes installed.'


class setupLDAPUPC(grok.View):
    """ Configure LDAPUPC for Plone instance """
    grok.context(IPloneSiteRoot)
    grok.require('zope2.ViewManagementScreens')

    def render(self):
        try:
            from plone.protect.interfaces import IDisableCSRFProtection
            alsoProvides(self.request, IDisableCSRFProtection)
        except:
            pass
        portal = getSite()

        if HAS_LDAP:
            try:
                manage_addPloneLDAPMultiPlugin(portal.acl_users, 'ldapUPC',
                    title='ldapUPC', use_ssl=1, login_attr='cn', uid_attr='cn', local_groups=0,
                    users_base='ou=Users,dc=upc,dc=edu', users_scope=2,
                    roles='Authenticated', groups_base='ou=Groups,dc=upc,dc=edu',
                    groups_scope=2, read_only=True, binduid='cn=ldap.serveis,ou=users,dc=upc,dc=edu', bindpwd=LDAP_PASSWORD,
                    rdn_attr='cn', LDAP_server='ldap.upc.edu', encryption='SSHA')
                portal.acl_users.ldapUPC.acl_users.manage_edit('ldapUPC', 'cn', 'cn', 'ou=Users,dc=upc,dc=edu', 2, 'Authenticated',
                    'ou=Groups,dc=upc,dc=edu', 2, 'cn=ldap.serveis,ou=users,dc=upc,dc=edu', LDAP_PASSWORD, 1, 'cn',
                    'top,person', 0, 0, 'SSHA', 1, '')
                plugin = portal.acl_users['ldapUPC']

                plugin.manage_activateInterfaces(['IGroupEnumerationPlugin', 'IGroupsPlugin', 'IGroupIntrospection', 'IAuthenticationPlugin', 'IUserEnumerationPlugin'])
                # Comentem la linia per a que no afegeixi
                # LDAPUserFolder.manage_addServer(portal.acl_users.ldapUPC.acl_users, 'ldap.upc.edu', '636', use_ssl=1)

                LDAPUserFolder.manage_deleteLDAPSchemaItems(portal.acl_users.ldapUPC.acl_users, ldap_names=['sn'], REQUEST=None)
                LDAPUserFolder.manage_addLDAPSchemaItem(portal.acl_users.ldapUPC.acl_users, ldap_name='sn', friendly_name='Last Name', public_name='name')

                # Move the ldapUPC to the top of the active plugins.
                # Otherwise member.getProperty('email') won't work properly.
                # from Products.PluggableAuthService.interfaces.plugins import IPropertiesPlugin
                # portal.acl_users.plugins.movePluginsUp(IPropertiesPlugin, ['ldapUPC'])
                # portal.acl_users.plugins.manage_movePluginsUp('IPropertiesPlugin', ['ldapUPC'], context.REQUEST.RESPONSE)

            except:
                logger.debug('Something bad happened and the LDAP has not been created properly')

            try:
                plugin = portal.acl_users['ldapUPC']
                plugin.ZCacheable_setManagerId('RAMCache')

                portal_role_manager = portal.acl_users['portal_role_manager']
                portal_role_manager.assignRolesToPrincipal(['Manager'], 'UPC.Plone.Admins')
                portal_role_manager.assignRolesToPrincipal(['Manager'], 'UPCnet.Plone.Admins')
                portal_role_manager.assignRolesToPrincipal(['Manager'], 'UPCnet.ATIC')
                portal_role_manager.assignRolesToPrincipal(['Manager'], 'UPCNET.Frontoffice.2n.nivell')

            except:
                logger.debug('Something bad happened and the LDAP has not been configured properly')

        else:
            logger.debug('You do not have LDAP libraries in your current buildout configuration. POSOK.')

            # try:
            # Fora el sistema de cookies que fan buscar al LDAP cn=*
            #     portal.acl_users.manage_delObjects('credentials_cookie_auth')
            # except:
            #     pass


class setupLDAPExterns(grok.View):
    """ Configure LDAPExterns for Plone instance """
    grok.context(IPloneSiteRoot)
    grok.require('zope2.ViewManagementScreens')

    def render(self):
        try:
            from plone.protect.interfaces import IDisableCSRFProtection
            alsoProvides(self.request, IDisableCSRFProtection)
        except:
            pass
        portal = getSite()

        # Delete the LDAPUPC if exists
        if getattr(portal.acl_users, 'ldapUPC', None):
            portal.acl_users.manage_delObjects('ldapUPC')

        # try:
        manage_addPloneLDAPMultiPlugin(portal.acl_users, 'ldapexterns',
            title='ldapexterns', use_ssl=1, login_attr='cn', uid_attr='cn', local_groups=0,
            users_base='ou=users,ou=upcnet,dc=upcnet,dc=es', users_scope=2,
            roles='Authenticated,Member', groups_base='ou=groups,ou=upcnet,dc=upcnet,dc=es',
            groups_scope=2, read_only=True, binduid='cn=ldap,ou=upcnet,dc=upcnet,dc=es', bindpwd=LDAP_PASSWORD,
            rdn_attr='cn', LDAP_server='ldap.upcnet.es', encryption='SSHA')
        portal.acl_users.ldapexterns.acl_users.manage_edit('ldapexterns', 'cn', 'cn', 'ou=users,ou=upcnet,dc=upcnet,dc=es', 2, 'Authenticated,Member',
            'ou=groups,ou=upcnet,dc=upcnet,dc=es', 2, 'cn=ldap,ou=upcnet,dc=upcnet,dc=es', LDAP_PASSWORD, 1, 'cn',
            'top,person,inetOrgPerson', 0, 0, 'SSHA', 0, '')

        plugin = portal.acl_users['ldapexterns']

        # Activate plugins (all)
        plugin.manage_activateInterfaces(['IAuthenticationPlugin',
                                          'ICredentialsResetPlugin',
                                          'IGroupEnumerationPlugin',
                                          'IGroupIntrospection',
                                          'IGroupManagement',
                                          'IGroupsPlugin',
                                          'IUserAdderPlugin',
                                          'IUserEnumerationPlugin',
                                          'IUserManagement'])

        # In case to have more than one server for fault tolerance
        # LDAPUserFolder.manage_addServer(portal.acl_users.ldapUPC.acl_users, "ldap.upc.edu", '636', use_ssl=1)

        # Redefine some schema properties
        LDAPUserFolder.manage_deleteLDAPSchemaItems(portal.acl_users.ldapexterns.acl_users, ldap_names=['sn'], REQUEST=None)
        LDAPUserFolder.manage_deleteLDAPSchemaItems(portal.acl_users.ldapexterns.acl_users, ldap_names=['cn'], REQUEST=None)
        LDAPUserFolder.manage_addLDAPSchemaItem(portal.acl_users.ldapexterns.acl_users, ldap_name='sn', friendly_name='Last Name', public_name='fullname')
        LDAPUserFolder.manage_addLDAPSchemaItem(portal.acl_users.ldapexterns.acl_users, ldap_name='cn', friendly_name='Canonical Name')

        # Update the preference of the plugins
        portal.acl_users.plugins.movePluginsUp(IUserAdderPlugin, ['ldapexterns'])
        portal.acl_users.plugins.movePluginsUp(IGroupManagement, ['ldapexterns'])

        # Move the ldapUPC to the top of the active plugins.
        # Otherwise member.getProperty('email') won't work properly.
        # from Products.PluggableAuthService.interfaces.plugins import IPropertiesPlugin
        # portal.acl_users.plugins.movePluginsUp(IPropertiesPlugin, ['ldapUPC'])
        # portal.acl_users.plugins.manage_movePluginsUp('IPropertiesPlugin', ['ldapUPC'], context.REQUEST.RESPONSE)
        # except:
        #     pass

        # Add LDAP plugin cache
        plugin = portal.acl_users['ldapexterns']
        plugin.ZCacheable_setManagerId('RAMCache')
        return 'Done.'


class setupLDAP(grok.View):
    """ Configure basic LDAP for Plone instance """
    grok.context(IPloneSiteRoot)
    grok.require('zope2.ViewManagementScreens')

    def render(self):
        try:
            from plone.protect.interfaces import IDisableCSRFProtection
            alsoProvides(self.request, IDisableCSRFProtection)
        except:
            pass
        portal = getSite()
        ldap_name = self.request.form.get('ldap_name', 'ldap')
        ldap_server = self.request.form.get('ldap_server')
        branch_name = self.request.form.get('branch_name')
        base_dn = self.request.form.get('base_dn')
        branch_admin_cn = self.request.form.get('branch_admin_cn')
        branch_admin_password = self.request.form.get('branch_admin_password')
        allow_manage_users = self.request.form.get('allow_manage_users', False)

        users_base = 'ou=users,ou={},{}'.format(branch_name, base_dn)
        groups_base = 'ou=groups,ou={},{}'.format(branch_name, base_dn)
        bind_uid = 'cn={},ou={},{}'.format(branch_admin_cn, branch_name, base_dn)

        # Delete if exists
        if getattr(portal.acl_users, ldap_name, None):
            portal.acl_users.manage_delObjects('ldapUPC')

        manage_addPloneLDAPMultiPlugin(
            portal.acl_users, ldap_name,
            use_ssl=1, login_attr='cn', uid_attr='cn', local_groups=0,
            rdn_attr='cn', encryption='SSHA', read_only=True,
            roles='Authenticated,Member', groups_scope=2, users_scope=2,
            title=ldap_name,
            LDAP_server=ldap_server,
            users_base=users_base,
            groups_base=groups_base,
            binduid=bind_uid,
            bindpwd=branch_admin_password)

        ldap_acl_users = getattr(portal.acl_users, ldap_name).acl_users
        ldap_acl_users.manage_edit(
            ldap_name, 'cn', 'cn', users_base, 2, 'Authenticated,Member',
            groups_base, 2, bind_uid, branch_admin_password, 1, 'cn',
            'top,person,inetOrgPerson', 0, 0, 'SSHA', 0, '')

        plugin = portal.acl_users[ldap_name]

        active_plugins = [
            'IAuthenticationPlugin', 'ICredentialsResetPlugin', 'IGroupEnumerationPlugin',
            'IGroupIntrospection', 'IGroupManagement', 'IGroupsPlugin',
            'IPropertiesPlugin', 'IRoleEnumerationPlugin', 'IRolesPlugin',
            'IUserAdderPlugin', 'IUserEnumerationPlugin']

        if allow_manage_users:
            active_plugins.append('IUserManagement')

        plugin.manage_activateInterfaces(active_plugins)

        # Redefine some schema properties

        LDAPUserFolder.manage_deleteLDAPSchemaItems(ldap_acl_users, ldap_names=['sn'], REQUEST=None)
        LDAPUserFolder.manage_deleteLDAPSchemaItems(ldap_acl_users, ldap_names=['cn'], REQUEST=None)
        LDAPUserFolder.manage_addLDAPSchemaItem(ldap_acl_users, ldap_name='sn', friendly_name='Last Name', public_name='fullname')
        LDAPUserFolder.manage_addLDAPSchemaItem(ldap_acl_users, ldap_name='cn', friendly_name='Canonical Name')

        # Update the preference of the plugins
        portal.acl_users.plugins.movePluginsUp(IUserAdderPlugin, [ldap_name])
        portal.acl_users.plugins.movePluginsUp(IGroupManagement, [ldap_name])

        # Add LDAP plugin cache
        plugin = portal.acl_users[ldap_name]
        plugin.ZCacheable_setManagerId('RAMCache')
        return 'Done.'


class view_user_catalog(grok.View):
    """ Rebuild the OMEGA13 repoze.catalog for user properties data """
    grok.context(IPloneSiteRoot)
    grok.name('view_user_catalog')
    grok.require('cmf.ManagePortal')

    @json_response
    def render(self):
        try:
            from plone.protect.interfaces import IDisableCSRFProtection
            alsoProvides(self.request, IDisableCSRFProtection)
        except:
            pass
        portal = api.portal.get()
        soup = get_soup('user_properties', portal)
        records = [r for r in soup.data.items()]

        result = {}
        for record in records:
            item = {}
            for key in record[1].attrs:
                item[key] = record[1].attrs[key]

            result[record[1].attrs['id']] = item

        return result


class reset_user_catalog(grok.View):
    """ Reset the OMEGA13 repoze.catalog for user properties data """

    grok.context(IPloneSiteRoot)
    grok.name('reset_user_catalog')
    grok.require('cmf.ManagePortal')

    def render(self):
        try:
            from plone.protect.interfaces import IDisableCSRFProtection
            alsoProvides(self.request, IDisableCSRFProtection)
        except:
            pass

        from base5.core.utils import reset_user_catalog
        reset_user_catalog()
        return 'Done.'


class rebuild_user_catalog(grok.View):
    """ Rebuild the OMEGA13 repoze.catalog for user properties data """
    grok.context(IPloneSiteRoot)
    grok.name('rebuild_user_catalog')
    grok.require('cmf.ManagePortal')

    def render(self):
        try:
            from plone.protect.interfaces import IDisableCSRFProtection
            alsoProvides(self.request, IDisableCSRFProtection)
        except:
            pass
        portal = api.portal.get()
        plugins = portal.acl_users.plugins.listPlugins(IPropertiesPlugin)
        # We use the most preferent plugin
        pplugin = plugins[0][1]
        all_user_properties = pplugin.enumerateUsers()

        for user in all_user_properties:
            user.update(dict(username=user['id']))
            if 'title' in user:
                user.update(dict(fullname=user['title']))
            elif 'fullname' in user:
                user.update(dict(fullname=user['fullname']))
            elif 'sn' in user:
                user.update(dict(fullname=user['sn']))
            else:
                user.update(dict(fullname=user['cn']))

            user_obj = api.user.get(user['id'])

            if user_obj:
                add_user_to_catalog(user_obj, user)
            else:
                print('No user found in user repository (LDAP) {}'.format(user['id']))

            print('Updated properties catalog for {}'.format(user['id']))