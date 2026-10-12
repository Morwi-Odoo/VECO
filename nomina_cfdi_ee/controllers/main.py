# -*- coding: utf-8 -*-
import os
import zipfile, tempfile
from pathlib import Path
from io import BytesIO

from odoo import http
from odoo.http import request


class BinaryCDFIInvoice(http.Controller):

    @http.route('/payroll/download_document', type='http', auth="public")
    def download_document(self, id=None, **kw):
        if id:
            payslip = request.env['hr.payslip.run'].browse(int(id))
            allowed_extension = ['.xml', '.pdf']
            # path = Path.home() / 'Downloads'
            filename = payslip.name.lower().replace(' ', '_') + '.zip'
            slips = payslip.slip_ids
            tmpfile = tempfile.NamedTemporaryFile()
            with tempfile.TemporaryDirectory() as tmpdir:
                zip_file = tmpfile  # os.path.join(path, filename)
                with zipfile.ZipFile(zip_file, 'w') as zfile:
                    for slip in slips:
                        docs = request.env['ir.attachment'].search(
                            ['&', ('res_model', '=', 'hr.payslip'), ('res_id', '=', slip.id)])
                        for doc in docs:
                            if any(doc.name.endswith(ext) for ext in allowed_extension):
                                temp = os.path.join(tmpdir, doc.name)  # path / doc.name
                                with open(temp, 'wb') as n_file:
                                    n_file.write(doc.raw)
                                zfile.write(temp, doc.name)
                                os.remove(temp)
                return http.send_file(zip_file, filename=filename, as_attachment=True)
        return request.not_found()
