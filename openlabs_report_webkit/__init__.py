# -*- coding: utf-8 -*-
'''


    :copyright: (c) 2013 by Openlabs Technologies & Consulting (P) Ltd.
    :license: GPLv3, see LICENSE for more details

'''

try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
import os
import time
import datetime
import tempfile
from functools import partial

from jinja2 import Environment, FunctionLoader
from babel.dates import format_date, format_datetime
from babel.numbers import format_currency

from genshi.template import MarkupTemplate
from trytond.modules import Index
from trytond.pool import Pool
from trytond.transaction import Transaction
from trytond.report import Report, TranslateFactory, Translator, FORMAT2EXT
from executor import execute
import weasyprint



class ReportWebkit(Report):

    @classmethod
    def parse(cls, report, records, data, localcontext):
        '''
        Parse the report and return a tuple with report type and report.
        '''
        pool = Pool()
        User = pool.get('res.user')
        Translation = pool.get('ir.translation')

        localcontext['data'] = data
        localcontext['user'] = User(Transaction().user)
        localcontext['formatLang'] = lambda *args, **kargs: \
            cls.format_lang(*args, **kargs)
        localcontext['StringIO'] = StringIO.StringIO
        localcontext['time'] = time
        localcontext['datetime'] = datetime
        localcontext['context'] = Transaction().context

        translate = TranslateFactory(cls.__name__, Transaction().language,
            Translation)
        localcontext['setLang'] = lambda language: translate.set_language(
            language)
        localcontext['records'] = records
        localcontext['file_path'] = Index().module_file

        # Convert to str as buffer from DB is not supported by StringIO
        report_content = (str(report.report_content) if report.report_content
            else False)

        if not report_content:
            raise Exception('Error', 'Missing report file!')

        result = cls.render_template(report_content, localcontext, translate)

        output_format = report.extension or report.template_extension
        if output_format in ('pdf',):
        #    result = cls.wkhtml_to_pdf(result)
            result = cls.weasyprint(result)

        # Check if the output_format has a different extension for it
        oext = FORMAT2EXT.get(output_format, output_format)
        return (oext, result)

    @classmethod
    def render_template_genshi(cls, template_string, localcontext, translator):
        """
        Legacy genshi rendered for backward compatibility. If your report is
        still dependent on genshi, implement the method render_template in
        your custom report and call this method with the same arguments and
        return the value instead.
        """
        report_template = MarkupTemplate(template_string)

        # Since Genshi >= 0.6, Translator requires a function type
        report_template.filters.insert(
            0, Translator(lambda text: translator(text))
        )

        stream = report_template.generate(**localcontext)

        return stream.render('xhtml').encode('utf-8')

    @classmethod
    def jinja_loader_func(cls, name):
        """
        Return the template from the module directories using the logic
        below:

        The name is expected to be in the format:

            <module_name>/path/to/template

        for example, if the account_reports module had a base template in
        its reports folder, then you should be able to use:

            {% extends 'account_reports/report/base.html' %}
        """
        try:
            with open(Index().module_file(name)) as f:
                return f.read()
        except IOError:
            return None

    @classmethod
    def get_jinja_filters(cls):
        """
        Returns filters that are made available in the template context.
        By default, the following filters are available:

        * dateformat: Formats a date using babel
        * datetimeformat: Formats a datetime using babel
        * currencyformat: Formats the given number as currency
        * modulepath: Returns the absolute path of a file inside a
            tryton-module (e.g. sale/sale.css)

        For additional arguments that can be passed to these filters,
        refer to the Babel `Documentation
        <http://babel.edgewall.org/wiki/Documentation>`_.
        """

        return {
            'dateformat': partial(format_date, locale=Transaction().language),
            'datetimeformat': partial(
                format_datetime, locale=Transaction().language
            ),
            'currencyformat': partial(
                format_currency, locale=Transaction().language
            ),
            'module_path': lambda f: 'file://' + Index().module_file(f)
        }

    @classmethod
    def render_template(cls, template_string, localcontext, translator):
        """
        Render the template using Jinja2
        """
        env = Environment(loader=FunctionLoader(cls.jinja_loader_func))
        env.filters.update(cls.get_jinja_filters())
        report_template = env.from_string(template_string.decode('utf-8'))
        return report_template.render(**localcontext).encode('utf-8')

    @classmethod
    def weasy_url(cls, url):
        if url.startswith('tryton://'):
            url = 'file://'+Index().module_file(url[9:])
        return weasyprint.default_url_fetcher(url)

    @classmethod
    def weasyprint(cls, data, options=None):
        return weasyprint.HTML(string=data, url_fetcher=cls.weasy_url).write_pdf()

    @classmethod
    def wkhtml_to_pdf(cls, data, options=None):
        """
        Call wkhtmltopdf to convert the html to pdf
        """
        with tempfile.NamedTemporaryFile(
            suffix='.html', prefix='trytond_', delete=False
        ) as source_file:
            file_name = source_file.name
            source_file.write(data)
            source_file.close()

            # Evaluate argument to run with subprocess
            args = 'wkhtmltopdf'
            # Add Global Options
            if options:
                for option, value in options.items():
                    args += ' --%s' % option
                    if value:
                        args += ' "%s"' % value

            args += ' -T 50mm'
            # Add source file name and output file name
            args += ' %s %s.pdf' % (file_name, file_name)
            # Execute the command using executor
            print(args)
            execute(args)
            return open(file_name + '.pdf').read()
