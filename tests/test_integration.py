#!/usr/bin/python3
from __future__ import print_function

import ast
import importlib.machinery
import os
import shutil
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
XFCE = ROOT
SYNC_PATH = ROOT / 'bin/minios-thunar-uca-sync'
ACTIONS_PATH = ROOT / 'bin/minios-thunar-actions'
LOCALE_DIR = Path(os.environ.get(
    'MINIOS_THUNAR_TEST_LOCALE_DIR', str(ROOT / 'build/locale')))

sync = importlib.machinery.SourceFileLoader(
    'minios_thunar_uca_sync', str(SYNC_PATH)).load_module()
actions = importlib.machinery.SourceFileLoader(
    'minios_thunar_actions', str(ACTIONS_PATH)).load_module()


def ids(root):
    return [item.findtext('unique-id') for item in root.findall('action')]


def semantic(element):
    return (
        element.tag, tuple(sorted(element.attrib.items())), element.text or '',
        tuple(semantic(child) for child in list(element)))


def action_by_id(root, unique_id):
    for item in root.findall('action'):
        if item.findtext('unique-id') == unique_id:
            return item
    return None


class UcaSyncTests(unittest.TestCase):
    def test_clean_file_gets_actions_and_second_sync_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'uca.xml')
            self.assertTrue(sync.sync_file(path, True))
            first = Path(path).read_bytes()
            root = ET.parse(path).getroot()
            self.assertEqual(ids(root), [
                sync.TERMINAL_ID, sync.CREATE_ID, sync.EXTRACT_ID,
                sync.ACTIVATE_ID, sync.DEACTIVATE_ID])
            self.assertFalse(sync.sync_file(path, True))
            self.assertEqual(Path(path).read_bytes(), first)

    def test_unknown_user_action_is_preserved_semantically(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'uca.xml')
            root = ET.Element('actions')
            user = ET.SubElement(root, 'action', {'custom': 'yes'})
            ET.SubElement(user, 'name').text = 'My Custom Action'
            ET.SubElement(user, 'unique-id').text = 'user-owned-id'
            ET.SubElement(user, 'command').text = 'printf %f'
            ET.SubElement(user, 'submenu').text = 'Tools'
            ET.SubElement(user, 'patterns').text = '*.txt'
            ET.SubElement(user, 'text-files')
            before = semantic(user)
            ET.ElementTree(root).write(path, encoding='UTF-8', xml_declaration=True)

            sync.sync_file(path, True)
            after_root = ET.parse(path).getroot()
            after = action_by_id(after_root, 'user-owned-id')
            self.assertIsNotNone(after)
            self.assertEqual(semantic(after), before)

    def test_user_action_order_is_preserved_across_minios_migration(self):
        root = ET.Element('actions')
        first = ET.SubElement(root, 'action')
        ET.SubElement(first, 'unique-id').text = 'user-first'
        legacy = ET.SubElement(root, 'action')
        ET.SubElement(legacy, 'unique-id').text = sync.CREATE_ID
        second = ET.SubElement(root, 'action')
        ET.SubElement(second, 'unique-id').text = 'user-second'
        legacy2 = ET.SubElement(root, 'action')
        ET.SubElement(legacy2, 'unique-id').text = sync.EXTRACT_ID
        third = ET.SubElement(root, 'action')
        ET.SubElement(third, 'unique-id').text = 'user-third'

        sync.sync_root(root, True)
        user_ids = [item.findtext('unique-id') for item in root.findall('action')
                    if item.findtext('unique-id') not in sync.KNOWN_IDS]
        self.assertEqual(user_ids, ['user-first', 'user-second', 'user-third'])

    def test_overlay_removes_only_runtime_actions(self):
        root = ET.Element('actions')
        sync.sync_root(root, True)
        sync.sync_root(root, False)
        self.assertEqual(ids(root), [
            sync.TERMINAL_ID, sync.CREATE_ID, sync.EXTRACT_ID])

    def test_applicability_matches_old_and_new_thunar(self):
        root = ET.Element('actions')
        sync.sync_root(root, True)
        create = action_by_id(root, sync.CREATE_ID)
        extract = action_by_id(root, sync.EXTRACT_ID)
        activate = action_by_id(root, sync.ACTIVATE_ID)
        deactivate = action_by_id(root, sync.DEACTIVATE_ID)
        self.assertEqual(create.findtext('patterns'), '*')
        self.assertIsNotNone(create.find('directories'))
        for item in (extract, activate, deactivate):
            self.assertEqual(item.findtext('patterns'), '*.sb')
            self.assertIsNotNone(item.find('other-files'))
        old_thunar_tags = {
            'actions', 'action', 'icon', 'name', 'unique-id', 'command',
            'description', 'patterns', 'startup-notify', 'directories',
            'audio-files', 'image-files', 'other-files', 'text-files',
            'video-files',
        }
        for element in root.iter():
            self.assertIn(element.tag, old_thunar_tags)

    def test_malformed_xml_is_not_destroyed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'uca.xml')
            original = b'<actions><action><broken></actions>\n'
            Path(path).write_bytes(original)
            with self.assertRaises(ValueError):
                sync.sync_file(path, True)
            self.assertEqual(Path(path).read_bytes(), original)

    def test_locale_change_updates_only_minios_actions(self):
        root = ET.Element('actions')
        user = ET.SubElement(root, 'action')
        ET.SubElement(user, 'unique-id').text = 'custom'
        ET.SubElement(user, 'name').text = 'Untouched'
        user_before = semantic(user)
        old_translation = sync._
        sync._ = lambda text: 'A:' + text
        sync.sync_root(root, True)
        first_name = action_by_id(root, sync.CREATE_ID).findtext('name')
        sync._ = lambda text: 'B:' + text
        sync.sync_root(root, True)
        second_name = action_by_id(root, sync.CREATE_ID).findtext('name')
        sync._ = old_translation
        self.assertTrue(first_name.startswith('A:'))
        self.assertTrue(second_name.startswith('B:'))
        self.assertEqual(semantic(action_by_id(root, 'custom')), user_before)

    def test_compiled_catalogs_exist_for_supported_languages(self):
        for language in ('de', 'es', 'fr', 'id', 'it', 'pt', 'pt_BR', 'ru'):
            catalog = LOCALE_DIR / language / 'LC_MESSAGES/minios-thunar-actions.mo'
            self.assertTrue(catalog.is_file(), str(catalog))

    def test_gettext_english_and_russian_names(self):
        old_language = os.environ.get('LANGUAGE')
        try:
            os.environ['LANGUAGE'] = 'en'
            en = sync.translator(str(LOCALE_DIR))
            self.assertEqual(en('Create Module…'), 'Create Module…')
            os.environ['LANGUAGE'] = 'ru'
            ru = sync.translator(str(LOCALE_DIR))
            self.assertEqual(ru('Create Module…'), 'Создать модуль…')
            self.assertEqual(ru('Extract Module…'), 'Извлечь модуль…')
        finally:
            if old_language is None:
                os.environ.pop('LANGUAGE', None)
            else:
                os.environ['LANGUAGE'] = old_language


    def test_findmnt_check_uses_fixed_argv(self):
        with mock.patch.object(sync, 'findmnt_path', return_value='/usr/bin/findmnt'), \
                mock.patch.object(sync.subprocess, 'check_output', return_value='aufs\n') as check:
            self.assertEqual(sync.root_fstype(), 'aufs')
        check.assert_called_once_with(
            ['/usr/bin/findmnt', '-rn', '--mountpoint', '/', '-o', 'FSTYPE'],
            universal_newlines=True, stderr=sync.subprocess.DEVNULL)
    def test_compiled_catalogs_match_po_sources(self):
        msgfmt = shutil.which('msgfmt')
        if msgfmt is None:
            self.skipTest('msgfmt is not installed')
        with tempfile.TemporaryDirectory() as directory:
            for po in sorted((XFCE / 'po').glob('*.po')):
                expected = Path(directory) / (po.stem + '.mo')
                subprocess.check_call([msgfmt, '-o', str(expected), str(po)])
                installed = LOCALE_DIR / po.stem / 'LC_MESSAGES/minios-thunar-actions.mo'
                self.assertEqual(expected.read_bytes(), installed.read_bytes(), po.name)



class FrontendTests(unittest.TestCase):
    def test_conversion_argv_preserves_spaces_unicode_and_dash_names(self):
        source = '/tmp/Каталог с пробелами/-источник'
        target = '/tmp/Результат с пробелами.sb'
        self.assertEqual(
            actions.build_conversion_argv('create', source, target),
            ['/usr/bin/dir2sb', '--json', '--', source, target])
        self.assertEqual(
            actions.build_conversion_argv('extract', target, source),
            ['/usr/bin/sb2dir', '--json', '--', target, source])

    def test_runtime_argv_is_fixed(self):
        path = '/tmp/модуль с пробелом/-test.sb'
        self.assertEqual(
            actions.build_runtime_argv('activate', path),
            ['/usr/bin/pkexec', '/usr/bin/sb', 'activate', path])
        self.assertEqual(
            actions.build_runtime_argv('deactivate', path),
            ['/usr/bin/pkexec', '/usr/bin/sb', 'deactivate', path])

    def test_subprocess_calls_never_use_shell_interpolation(self):
        tree = ast.parse(ACTIONS_PATH.read_text())
        calls = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in ('Popen', 'check_output'):
                calls.append(node)
                self.assertFalse(any(keyword.arg == 'shell' for keyword in node.keywords))
        self.assertGreaterEqual(len(calls), 3)


    def test_default_targets_are_siblings(self):
        self.assertEqual(
            actions.default_create_target('/home/live/work/firefox/'),
            '/home/live/work/firefox.sb')
        self.assertEqual(
            actions.default_extract_target('/home/live/work/firefox.sb'),
            '/home/live/work/firefox')

    def test_runtime_action_rechecks_aufs_before_starting_backend(self):
        with mock.patch.object(actions, 'root_fstype', return_value='overlay'), \
                mock.patch.object(actions, 'show_error') as error, \
                mock.patch.object(actions, 'RuntimeJob') as runtime:
            self.assertEqual(actions.run_runtime_action('activate', '/tmp/test.sb'), 1)
        runtime.assert_not_called()
        error.assert_called_once()

    def test_conversion_dialog_uses_activity_indicator_and_action_area_cancel(self):
        source = ACTIONS_PATH.read_text()
        self.assertIn('self.progress = Gtk.ProgressBar()', source)
        self.assertIn('self.progress.pulse()', source)
        self.assertIn('GLib.timeout_add(90, self._pulse)', source)
        self.assertIn('action_area = self.dialog.get_action_area()', source)
        self.assertNotIn('Gtk.Spinner()', source)
        self.assertNotIn('set_fraction(', source)

class PackageLayoutTests(unittest.TestCase):
    def test_session_hooks_are_packaged(self):
        early = ROOT / 'share/X11/Xsession.d/65minios-thunar-uca-sync'
        autostart = ROOT / 'share/xdg/autostart/minios-thunar-uca-sync.desktop'
        self.assertTrue(early.is_file())
        self.assertTrue(autostart.is_file())
        self.assertIn('/usr/bin/minios-thunar-uca-sync', early.read_text())
        self.assertIn('OnlyShowIn=XFCE;', autostart.read_text())

    def test_package_does_not_register_a_module_mime_type(self):
        files = [SYNC_PATH, ACTIONS_PATH]
        files.extend((ROOT / 'share').rglob('*'))
        content = '\n'.join(
            path.read_text(errors='ignore') for path in files if path.is_file())
        self.assertNotIn('application/x-minios-module', content)
        self.assertNotIn('<mime-type', content)

    def test_makefile_installs_only_thin_frontend_assets(self):
        makefile = (ROOT / 'Makefile').read_text()
        self.assertIn('minios-thunar-actions', makefile)
        self.assertIn('minios-thunar-uca-sync', makefile)
        self.assertIn('Xsession.d', makefile)
        self.assertNotIn('dir2sb.py', makefile)
        self.assertNotIn('sb2dir.py', makefile)


if __name__ == '__main__':
    unittest.main()
