// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

// Visual editor for the Automation add-on workflow field.

(() => {
  const SECTIONS = ["triggers", "conditions", "actions"];
  const DISCRIMINATORS = {
    triggers: "trigger",
    conditions: "condition",
    actions: "action",
  };
  const WORKFLOW_KEYS = ["version", "triggers", "conditions", "actions"];

  const isPlainObject = (value) =>
    typeof value === "object" && value !== null && !Array.isArray(value);

  function init() {
    const editor = document.querySelector("[data-automation-editor]");
    const form = document.querySelector("#addon-form");
    if (!editor || !form || typeof jsyaml === "undefined") {
      return;
    }
    const field = form.querySelector("textarea[name='workflow']");
    const chromeTemplate = document.querySelector(
      "template[data-automation-chrome]",
    );
    if (!field || !chromeTemplate) {
      return;
    }

    const yamlPane =
      document.getElementById("div_id_workflow") ?? field.parentElement;
    const nodePane = editor.querySelector("[data-automation-pane='editor']");
    const alertBox = editor.querySelector("[data-automation-alert]");
    const status = editor.querySelector("[data-automation-status]");
    const modeInputs = editor.querySelectorAll("input[name='automation_mode']");

    const templates = new Map();
    for (const template of document.querySelectorAll(
      "template[data-automation-node]",
    )) {
      templates.set(template.dataset.automationNode, template);
    }

    const lists = new Map(
      SECTIONS.map((section) => [
        section,
        editor.querySelector(`[data-automation-list='${section}']`),
      ]),
    );
    if (Array.from(lists.values()).some((list) => list === null)) {
      return;
    }

    let counter = 0;

    /* Cloned fields share the identifiers Django generated for the template,
     * so make them unique per node and keep labels and help texts pointing at
     * the right control. Radio and checkbox groups need a name to stay grouped,
     * so they get a prefixed one; every other control loses its name, as the
     * workflow is submitted through the `workflow` field alone. */
    function rewriteIdentifiers(root, prefix) {
      const renamed = new Map();
      for (const element of root.querySelectorAll("[id]")) {
        const next = `${prefix}-${element.id}`;
        renamed.set(element.id, next);
        element.id = next;
      }
      for (const label of root.querySelectorAll("label[for]")) {
        const target = renamed.get(label.htmlFor);
        if (target) {
          label.htmlFor = target;
        }
      }
      for (const element of root.querySelectorAll("[aria-describedby]")) {
        element.setAttribute(
          "aria-describedby",
          element
            .getAttribute("aria-describedby")
            .split(/\s+/)
            .map((token) => renamed.get(token) ?? token)
            .join(" "),
        );
      }
      for (const element of root.querySelectorAll("[name]")) {
        if (element.type === "radio" || element.type === "checkbox") {
          element.name = `${prefix}-${element.name}`;
        } else {
          element.removeAttribute("name");
        }
      }
    }

    function nodeControls(node) {
      return Array.from(node.querySelectorAll("[data-workflow-key]")).filter(
        (element) => element.closest("[data-automation-instance]") === node,
      );
    }

    function controlGroups(node) {
      const groups = new Map();
      for (const element of nodeControls(node)) {
        const container = element.closest("[data-automation-group]");
        const group =
          container !== null &&
          container.closest("[data-automation-instance]") === node
            ? container.dataset.automationGroup
            : null;
        const key = element.dataset.workflowKey;
        const identifier = `${group ?? ""}.${key}`;
        if (!groups.has(identifier)) {
          groups.set(identifier, {
            group,
            key,
            type: element.dataset.workflowType,
            required: element.dataset.workflowRequired === "1",
            elements: [],
          });
        }
        groups.get(identifier).elements.push(element);
      }
      return Array.from(groups.values());
    }

    function setGroupValue(entry, value) {
      const [first] = entry.elements;
      const wanted = (Array.isArray(value) ? value : [value]).map(String);
      if (first.type === "radio" || first.type === "checkbox") {
        const offered = new Set();
        for (const element of entry.elements) {
          element.checked = wanted.includes(element.value);
          if (element.checked) {
            offered.add(element.value);
          }
        }
        return offered.size === new Set(wanted).size;
      }
      if (first.multiple) {
        const offered = new Set(
          Array.from(first.options, (option) => option.value),
        );
        for (const option of first.options) {
          option.selected = wanted.includes(option.value);
        }

        for (const item of wanted) {
          if (!offered.has(item)) {
            const option = document.createElement("option");
            option.value = item;
            option.textContent = item;
            option.selected = true;
            first.append(option);
          }
        }
        return true;
      }
      const text = value === null || value === undefined ? "" : String(value);
      if (first.tagName === "SELECT") {
        first.value = text;
        return first.value === text;
      }
      first.value = text;
      return true;
    }

    function clearGroupValue(entry) {
      const [first] = entry.elements;
      if (first.type === "radio" || first.type === "checkbox") {
        for (const element of entry.elements) {
          element.checked = false;
        }
        return;
      }
      if (first.multiple) {
        for (const option of first.options) {
          option.selected = false;
        }
        return;
      }
      if (first.tagName === "SELECT") {
        if (Array.from(first.options, (option) => option.value).includes("")) {
          first.value = "";
        }
        return;
      }
      first.value = "";
    }

    function readGroupValue(entry) {
      const [first] = entry.elements;
      if (entry.type === "list") {
        const values =
          first.type === "checkbox"
            ? entry.elements
                .filter((element) => element.checked)
                .map((element) => element.value)
            : Array.from(first.selectedOptions, (option) => option.value);
        return values.length > 0 || entry.required ? values : undefined;
      }
      let raw;
      if (first.type === "radio") {
        raw = entry.elements.find((element) => element.checked)?.value ?? "";
      } else {
        raw = first.value;
      }
      raw = raw.trim();
      if (raw === "") {
        return entry.required ? "" : undefined;
      }
      if (entry.type === "integer") {
        const parsed = Number.parseInt(raw, 10);
        return Number.isNaN(parsed) ? raw : parsed;
      }
      return raw;
    }

    function applyValues(node, data, fresh) {
      const emitted = JSON.parse(node.dataset.automationEmit);
      const rendered = new Map([["", new Set(Object.keys(emitted))]]);
      for (const entry of controlGroups(node)) {
        const container = entry.group ?? "";
        if (!rendered.has(container)) {
          rendered.set(container, new Set());
        }
        rendered.get(container).add(entry.key);
        const source = entry.group ? data[entry.group] : data;
        const value = isPlainObject(source) ? source[entry.key] : undefined;
        if (value === undefined || value === null) {
          if (!fresh) {
            clearGroupValue(entry);
          }
          continue;
        }
        if (!setGroupValue(entry, value)) {
          return null;
        }
      }
      const extra = {};
      for (const [key, value] of Object.entries(data)) {
        const group = rendered.get(key);
        if (group !== undefined && key !== "" && isPlainObject(value)) {
          const leftover = {};
          for (const [name, item] of Object.entries(value)) {
            if (!group.has(name)) {
              leftover[name] = item;
            }
          }
          if (Object.keys(leftover).length > 0) {
            extra[key] = leftover;
          }
        } else if (!rendered.get("").has(key)) {
          extra[key] = value;
        }
      }
      return extra;
    }

    function serializeNode(node) {
      const result = JSON.parse(node.dataset.automationEmit);
      for (const [key, value] of Object.entries(
        JSON.parse(node.dataset.automationExtra || "{}"),
      )) {
        if (isPlainObject(value) && isPlainObject(result[key])) {
          Object.assign(result[key], value);
        } else {
          result[key] = value;
        }
      }
      for (const entry of controlGroups(node)) {
        const value = readGroupValue(entry);
        if (value === undefined) {
          continue;
        }
        if (entry.group) {
          result[entry.group] ??= {};
          result[entry.group][entry.key] = value;
        } else {
          result[entry.key] = value;
        }
      }
      return result;
    }

    function createNode(kind, data, fresh = false) {
      const template = templates.get(kind);
      if (template === undefined) {
        return null;
      }
      const node = chromeTemplate.content.firstElementChild.cloneNode(true);
      node.dataset.automationInstance = kind;
      node.dataset.automationEmit = template.dataset.automationEmit;
      node.querySelector("[data-automation-legend]").textContent =
        template.dataset.automationTitle;
      const fields = node.querySelector("[data-automation-fields]");
      fields.append(template.content.cloneNode(true));
      counter += 1;
      rewriteIdentifiers(fields, `automation-${counter}`);
      const extra = applyValues(node, data, fresh);
      if (extra === null) {
        return null;
      }
      node.dataset.automationExtra = JSON.stringify(extra);
      if (fields.childElementCount === 0) {
        fields.remove();
      }
      return node;
    }

    function nodeKind(item, discriminator) {
      if (!isPlainObject(item)) {
        return null;
      }
      if (discriminator === "action") {
        if (typeof item.action === "string") {
          return `action:${item.action}`;
        }
        if ("sequence" in item) {
          return "action:sequence";
        }
        if ("choose" in item) {
          return "action:choose";
        }
        return null;
      }
      const value = item[discriminator];
      return typeof value === "string" ? `${discriminator}:${value}` : null;
    }

    function buildTree(workflow) {
      if (!isPlainObject(workflow)) {
        return false;
      }
      if (Object.keys(workflow).some((key) => !WORKFLOW_KEYS.includes(key))) {
        return false;
      }
      if (workflow.version !== undefined && workflow.version !== 1) {
        return false;
      }
      const built = new Map();
      for (const section of SECTIONS) {
        const value = workflow[section];
        if (value === undefined) {
          built.set(section, []);
          continue;
        }
        if (!Array.isArray(value)) {
          return false;
        }
        const nodes = [];
        for (const item of value) {
          const kind = nodeKind(item, DISCRIMINATORS[section]);
          const node = kind === null ? null : createNode(kind, item);
          if (node === null) {
            return false;
          }
          nodes.push(node);
        }
        built.set(section, nodes);
      }
      for (const [section, nodes] of built) {
        lists.get(section).replaceChildren(...nodes);
        for (const node of nodes) {
          notifyAdded(node);
        }
      }
      return true;
    }

    function serializeWorkflow() {
      const collect = (section) =>
        Array.from(lists.get(section).children, serializeNode);
      const workflow = { version: 1, triggers: collect("triggers") };
      const conditions = collect("conditions");
      if (conditions.length > 0) {
        workflow.conditions = conditions;
      }
      workflow.actions = collect("actions");
      return workflow;
    }

    function toYaml(workflow) {
      return jsyaml.dump(workflow, { noRefs: true, lineWidth: -1, indent: 2 });
    }

    function parseField() {
      try {
        const value = jsyaml.load(field.value, { schema: jsyaml.JSON_SCHEMA });
        return value === undefined || value === null ? {} : value;
      } catch {
        return undefined;
      }
    }

    function notifyAdded(root) {
      document.dispatchEvent(
        new CustomEvent("weblate:content-added", { detail: { root } }),
      );
    }

    function announce(message) {
      if (status) {
        status.textContent = message;
      }
    }

    function showAlert(message) {
      alertBox.textContent = message;
      alertBox.hidden = false;
    }

    let mode = null;

    function applyMode(next) {
      mode = next;
      nodePane.hidden = next !== "editor";
      yamlPane.hidden = next === "editor";
      for (const input of modeInputs) {
        input.checked = input.value === next;
      }
    }

    function syncField() {
      field.value = toYaml(serializeWorkflow());
    }

    function setMode(next) {
      if (next !== "editor") {
        if (mode === "editor") {
          syncField();
        }
        alertBox.hidden = true;
        applyMode("yaml");
        return true;
      }
      const workflow = parseField();
      if (workflow === undefined) {
        showAlert(
          gettext(
            "This workflow is not valid YAML, so the editor cannot show it.",
          ),
        );
      } else if (!buildTree(workflow)) {
        showAlert(
          gettext(
            "This workflow uses parts the editor does not handle yet, such as nested conditions or branches. Edit it as YAML.",
          ),
        );
      } else {
        alertBox.hidden = true;
        applyMode("editor");
        return true;
      }
      applyMode("yaml");
      return false;
    }

    for (const input of modeInputs) {
      input.addEventListener("change", () => {
        if (input.checked) {
          setMode(input.value);
        }
      });
    }

    editor.addEventListener("click", (event) => {
      const add = event.target.closest("[data-automation-add]");
      if (add !== null) {
        const section = add.dataset.automationAdd;
        const picker = editor.querySelector(
          `[data-automation-picker='${section}']`,
        );
        const node = createNode(picker.value, {}, true);
        if (node === null) {
          return;
        }
        lists.get(section).append(node);
        notifyAdded(node);
        announce(
          interpolate(gettext("Added %s."), [
            picker.options[picker.selectedIndex].textContent.trim(),
          ]),
        );
        node.querySelector("input, select, textarea")?.focus();
        return;
      }
      const remove = event.target.closest("[data-automation-remove]");
      if (remove !== null) {
        const node = remove.closest("[data-automation-instance]");
        const label = node.querySelector(
          "[data-automation-legend]",
        ).textContent;
        node.remove();
        announce(interpolate(gettext("Removed %s."), [label]));
        return;
      }
      const move = event.target.closest("[data-automation-move]");
      if (move !== null) {
        const node = move.closest("[data-automation-instance]");
        const offset = Number.parseInt(move.dataset.automationMove, 10);
        const sibling =
          offset < 0 ? node.previousElementSibling : node.nextElementSibling;
        if (sibling === null) {
          return;
        }
        if (offset < 0) {
          sibling.before(node);
        } else {
          sibling.after(node);
        }
        const selector = `[data-automation-move='${move.dataset.automationMove}']`;
        node.querySelector(selector).focus();
        announce(
          interpolate(gettext("Moved %s."), [
            node.querySelector("[data-automation-legend]").textContent,
          ]),
        );
      }
    });

    form.addEventListener("submit", () => {
      if (!nodePane.hidden) {
        syncField();
      }
    });

    form.noValidate = true;
    editor.hidden = false;
    setMode(
      yamlPane.querySelector(".is-invalid, .invalid-feedback") === null
        ? "editor"
        : "yaml",
    );

    window.automationEditor = { serializeWorkflow, toYaml, buildTree, setMode };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
