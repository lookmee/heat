# vim: tabstop=4 shiftwidth=4 softtabstop=4

#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import mock
import os
import testtools
import testscenarios
import yaml

from heat.engine import clients
from heat.common import config
from heat.common import exception
from heat.common import template_format
from heat.tests.common import HeatTestCase
from heat.tests import utils

load_tests = testscenarios.load_tests_apply_scenarios


class JsonToYamlTest(HeatTestCase):

    def setUp(self):
        super(JsonToYamlTest, self).setUp()
        self.expected_test_count = 2
        self.longMessage = True
        self.maxDiff = None

    def test_convert_all_templates(self):
        path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                            'templates')

        template_test_count = 0
        for (json_str,
             yml_str,
             file_name) in self.convert_all_json_to_yaml(path):

            self.compare_json_vs_yaml(json_str, yml_str, file_name)
            template_test_count += 1
            if template_test_count >= self.expected_test_count:
                break

        self.assertTrue(template_test_count >= self.expected_test_count,
                        'Expected at least %d templates to be tested, not %d' %
                        (self.expected_test_count, template_test_count))

    def compare_json_vs_yaml(self, json_str, yml_str, file_name):
        yml = template_format.parse(yml_str)

        self.assertEqual(u'2012-12-12', yml[u'HeatTemplateFormatVersion'],
                         file_name)
        self.assertFalse(u'AWSTemplateFormatVersion' in yml, file_name)
        del(yml[u'HeatTemplateFormatVersion'])

        jsn = template_format.parse(json_str)
        template_format.default_for_missing(jsn, 'AWSTemplateFormatVersion',
                                            template_format.CFN_VERSIONS)

        if u'AWSTemplateFormatVersion' in jsn:
            del(jsn[u'AWSTemplateFormatVersion'])

        self.assertEqual(yml, jsn, file_name)

    def convert_all_json_to_yaml(self, dirpath):
        for path in os.listdir(dirpath):
            if not path.endswith('.template') and not path.endswith('.json'):
                continue
            f = open(os.path.join(dirpath, path), 'r')
            json_str = f.read()

            yml_str = template_format.convert_json_to_yaml(json_str)
            yield (json_str, yml_str, f.name)


class YamlMinimalTest(HeatTestCase):

    def test_minimal_yaml(self):
        yaml1 = ''
        yaml2 = '''HeatTemplateFormatVersion: '2012-12-12'
Parameters: {}
Mappings: {}
Resources: {}
Outputs: {}
'''
        tpl1 = template_format.parse(yaml1)
        tpl2 = template_format.parse(yaml2)
        self.assertEqual(tpl1, tpl2)

    def test_long_yaml(self):
        template = {'HeatTemplateVersion': '2012-12-12'}
        config.cfg.CONF.set_override('max_template_size', 1024)
        template['Resources'] = ['a'] * (config.cfg.CONF.max_template_size / 3)
        limit = config.cfg.CONF.max_template_size
        long_yaml = yaml.safe_dump(template)
        self.assertTrue(len(long_yaml) > limit)
        ex = self.assertRaises(exception.RequestLimitExceeded,
                               template_format.parse, long_yaml)
        msg = 'Request limit exceeded: Template exceeds maximum allowed size.'
        self.assertEqual(msg, str(ex))


class YamlParseExceptions(HeatTestCase):

    scenarios = [
        ('scanner', dict(raised_exception=yaml.scanner.ScannerError())),
        ('parser', dict(raised_exception=yaml.parser.ParserError())),
        ('reader',
         dict(raised_exception=yaml.reader.ReaderError('', '', '', '', ''))),
    ]

    def test_parse_to_value_exception(self):
        text = 'not important'

        with mock.patch.object(yaml, 'load') as yaml_loader:
            yaml_loader.side_effect = self.raised_exception

            self.assertRaises(ValueError,
                              template_format.parse, text)


class JsonYamlResolvedCompareTest(HeatTestCase):

    def setUp(self):
        super(JsonYamlResolvedCompareTest, self).setUp()
        self.longMessage = True
        self.maxDiff = None
        utils.setup_dummy_db()

    def load_template(self, file_name):
        filepath = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                'templates', file_name)
        f = open(filepath)
        t = template_format.parse(f.read())
        f.close()
        return t

    def compare_stacks(self, json_file, yaml_file, parameters):
        t1 = self.load_template(json_file)
        template_format.default_for_missing(t1, 'AWSTemplateFormatVersion',
                                            template_format.CFN_VERSIONS)
        del(t1[u'AWSTemplateFormatVersion'])

        t2 = self.load_template(yaml_file)
        del(t2[u'HeatTemplateFormatVersion'])

        stack1 = utils.parse_stack(t1, parameters)
        stack2 = utils.parse_stack(t2, parameters)

        # compare resources separately so that resolved static data
        # is compared
        t1nr = dict(stack1.t.t)
        del(t1nr['Resources'])

        t2nr = dict(stack2.t.t)
        del(t2nr['Resources'])
        self.assertEqual(t1nr, t2nr)

        self.assertEqual(set(stack1.keys()), set(stack2.keys()))
        for key in stack1:
            self.assertEqual(stack1[key].t, stack2[key].t)

    @testtools.skipIf(clients.neutronclient is None,
                      'neutronclient unavailable')
    def test_neutron_resolved(self):
        self.compare_stacks('Neutron.template', 'Neutron.yaml', {})

    def test_wordpress_resolved(self):
        self.compare_stacks('WordPress_Single_Instance.template',
                            'WordPress_Single_Instance.yaml',
                            {'KeyName': 'test'})
