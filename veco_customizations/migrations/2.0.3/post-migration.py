# -*- coding: utf-8 -*-
# Copyright 2026 Morwi Encoders Consulting SA de CV
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
"""Fix the Studio-customized MRP order QWeb reports (and one list view
overlay) for Odoo 19.

``mrp.production.date_planned_start``/``date_planned_finished`` were renamed
to ``date_start``/``date_finished`` by Odoo core. The Studio-generated
"report_mrporder" duplicates (``mrp.report_mrporder`` itself was never
touched, but the ``ir.ui.view`` records Studio created by duplicating it
were) and the Studio overlay on top of it still reference the old field
names, so printing any of these reports raises
``KeyError: 'date_planned_start'``. The Studio overlay on the
``mrp.production`` list view has the same problem in an
``xpath expr="//field[@name='date_planned_start']"``, which raises a
"cannot be located in parent view" error when that view is loaded.

Several of these views carry both an ``en_US`` and an ``es_MX`` translation
in ``arch_db``. ``ir.ui.view.arch`` (get/set) only reads/writes the
translation for the environment's current language, so fixing it through
that field would silently leave the other translation broken (and es_MX is
the one actually served to users). Patch ``arch_db`` directly with raw SQL
instead, so every stored translation gets the same fix.

Also reapplies every Studio/manual view edit made directly in the
Pruebas2025 test database after the 2026-07-07 migration (data-driven, see
``_apply_studio_views_fixup`` and ``studio_views_fixup.json``), since those
edits don't exist in the production source and would be lost on a fresh
migration run.

Also relaxes ``required`` back to ``False`` on the two manual (Studio)
fields listed in ``RELAXED_REQUIRED_FIELDS``, which were manually loosened
in that same test database after the migration.
"""

import json
import logging
import os

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# (old, new) literal replacements, applied to every stored translation of
# every affected view: each is a no-op if the pattern isn't present.
LITERAL_FIXES = [
    ('t-field="o.date_planned_start"', 't-field="o.date_start"'),
    ('t-field="o.date_planned_finished"', 't-field="o.date_finished"'),
    ('t-if="o.date_planned_start"', 't-if="o.date_start"'),
    ('t-if="o.date_planned_finished"', 't-if="o.date_finished"'),
]

XPATH_FIXES = [
    (
        "expr=\"//field[@name='date_planned_start']\"",
        "expr=\"//field[@name='date_start']\"",
    ),
]

# ir.ui.view.key of the Studio-duplicated report_mrporder views.
REPORT_VIEW_KEYS = [
    "mrp.report_mrporder_copy_1",
    "mrp.report_mrporder_copy_2",
    "mrp.report_mrporder_copy_3",
    "mrp.report_mrporder_copy_4",
    "mrp.report_mrporder_copy_1_copy_1",
    "mrp.report_mrporder_copy_1_copy_2",
    "mrp.report_mrporder_copy_1_copy_1_copy_1",
    "mrp.report_mrporder_copy_1_copy_2_copy_1",
    "mrp.report_mrporder_copy_1_copy_2_copy_2",
    "mrp.report_mrporder_copy_1_copy_3",
    "mrp.report_mrporder_copy_1_copy_4",
]

# ir.ui.view.name of the anonymous ("Odoo Studio: ... customization") overlay
# views: these don't have a `key`, but their `name` is unique.
OVERLAY_VIEW_NAMES = [
    "Odoo Studio: report_mrporder customization",
    "Odoo Studio: report_mrporder copy(1) customization",
]

TREE_OVERLAY_NAME = "Odoo Studio: mrp.production.tree customization"

# (model, field name) of manual (Studio-created) fields whose `required`
# flag was manually relaxed to False in the Pruebas2025 test database after
# the 2026-07-07 migration. Both are ``state == 'manual'`` fields, so the
# stored ``ir.model.fields.required`` value is authoritative at runtime
# (unlike for Python-defined fields, where it's informational only).
RELAXED_REQUIRED_FIELDS = [
    ("hr.expense", "x_name"),
    ("stock.move", "x_studio_supply_method"),
]


def _patch_view(cr, view_id, fixes):
    cr.execute("SELECT arch_db FROM ir_ui_view WHERE id = %s", (view_id,))
    row = cr.fetchone()
    if not row or not row[0]:
        return
    arch_db = row[0]
    changed = False
    for lang, arch in arch_db.items():
        if not arch:
            continue
        new_arch = arch
        for old, new in fixes:
            new_arch = new_arch.replace(old, new)
        if new_arch != arch:
            arch_db[lang] = new_arch
            changed = True
    if changed:
        cr.execute(
            "UPDATE ir_ui_view SET arch_db = %s WHERE id = %s",
            (json.dumps(arch_db), view_id),
        )


def _set_arch_db(cr, view_id, arch_by_lang):
    """Unconditionally overwrite every stored translation of a view's arch,
    bypassing ``ir.ui.view.arch`` (which only touches the current language).
    """
    cr.execute(
        "UPDATE ir_ui_view SET arch_db = %s WHERE id = %s",
        (json.dumps(arch_by_lang), view_id),
    )


def _apply_studio_views_fixup(cr, env):
    """Re-apply the Studio/manual view edits made in the Pruebas2025 test
    database after the 2026-07-07 migration to Odoo 19. Those edits only
    exist in that test database, so a fresh migration run from the
    production source would otherwise lose them again.

    Fixture generated via RPC from the Pruebas2025 instance; see
    ``studio_views_fixup.json`` next to this file.
    """
    fixup_path = os.path.join(os.path.dirname(__file__), "studio_views_fixup.json")
    with open(fixup_path, encoding="utf-8") as f:
        entries = json.load(f)

    ImdModel = env["ir.model.data"]
    ViewModel = env["ir.ui.view"]

    for entry in entries:
        xmlid = f"{entry['module']}.{entry['xmlid']}"
        if entry["action"] == "patch":
            cr.execute(
                "SELECT res_id FROM ir_model_data WHERE module = %s AND name = %s",
                (entry["module"], entry["xmlid"]),
            )
            row = cr.fetchone()
            if not row:
                _logger.warning(
                    "studio_views_fixup: %s not found, skipping patch", xmlid
                )
                continue
            _set_arch_db(cr, row[0], entry["arch_db"])

        elif entry["action"] == "create":
            if ImdModel.search([
                ("module", "=", entry["module"]),
                ("name", "=", entry["xmlid"]),
            ], limit=1):
                _logger.info("studio_views_fixup: %s already exists, skipping create", xmlid)
                continue
            inherit_xmlid = f"{entry['inherit_module']}.{entry['inherit_name']}"
            inherit_view = env.ref(inherit_xmlid, raise_if_not_found=False)
            if not inherit_view:
                _logger.warning(
                    "studio_views_fixup: base view %s not found, skipping create of %s",
                    inherit_xmlid, xmlid,
                )
                continue
            try:
                with cr.savepoint():
                    new_view = ViewModel.create({
                        "name": entry["name"],
                        "model": entry["model"],
                        "type": entry["type"],
                        "mode": entry["mode"],
                        "priority": entry["priority"],
                        "active": entry["active"],
                        "inherit_id": inherit_view.id,
                        "arch_db": next(iter(entry["arch_db"].values()), "<data/>"),
                    })
                    _set_arch_db(cr, new_view.id, entry["arch_db"])
                    ImdModel.create({
                        "module": entry["module"],
                        "name": entry["xmlid"],
                        "model": "ir.ui.view",
                        "res_id": new_view.id,
                        "noupdate": True,
                    })
            except Exception:
                _logger.warning(
                    "studio_views_fixup: failed to create %s, skipping", xmlid,
                    exc_info=True,
                )


def _apply_relaxed_required_fields(env):
    FieldModel = env["ir.model.fields"]
    for model, name in RELAXED_REQUIRED_FIELDS:
        field = FieldModel.search([("model", "=", model), ("name", "=", name)], limit=1)
        if not field:
            _logger.warning(
                "RELAXED_REQUIRED_FIELDS: %s.%s not found, skipping", model, name
            )
            continue
        if field.required:
            field.required = False


def migrate(cr, version):
    for key in REPORT_VIEW_KEYS:
        cr.execute("SELECT id FROM ir_ui_view WHERE key = %s", (key,))
        row = cr.fetchone()
        if row:
            _patch_view(cr, row[0], LITERAL_FIXES)

    for name in OVERLAY_VIEW_NAMES:
        cr.execute("SELECT id FROM ir_ui_view WHERE name = %s", (name,))
        row = cr.fetchone()
        if row:
            _patch_view(cr, row[0], LITERAL_FIXES)

    cr.execute("SELECT id FROM ir_ui_view WHERE name = %s", (TREE_OVERLAY_NAME,))
    row = cr.fetchone()
    if row:
        _patch_view(cr, row[0], XPATH_FIXES)

    env = api.Environment(cr, SUPERUSER_ID, {})
    _apply_studio_views_fixup(cr, env)
    _apply_relaxed_required_fields(env)
