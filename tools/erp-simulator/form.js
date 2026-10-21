/*
 * Typed request-form renderer.
 *
 * Turns an endpoint's declarative `body` schema into real HTML inputs and turns
 * the entered values back into the JSON payload the API expects. Values are kept
 * as strings while editing; they are coerced to int/float/bool on build.
 */
(function () {
  "use strict";

  const humanize = (name) => name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  const ARRAY_SHAPES = { "object-array": true, array: true, "string-array": true };

  function emptyRow(fields) {
    const row = {};
    (fields || []).forEach((field) => {
      row[field.name] = field.default !== undefined ? String(field.default) : "";
    });
    return row;
  }

  function initState(ep) {
    const body = ep.body || { shape: "none" };
    const state = { values: {}, rows: [] };
    if (body.shape === "object") {
      (body.fields || []).forEach((field) => {
        state.values[field.name] = field.default !== undefined ? String(field.default) : "";
      });
    }
    if (body.shape === "string-array") {
      state.rows = [{ __value: body.default || "" }];
    } else if (ARRAY_SHAPES[body.shape]) {
      state.rows = [emptyRow(body.itemFields)];
    }
    return state;
  }

  function sectionOrder(fields) {
    const order = [];
    fields.forEach((field) => {
      const name = field.section || "Details";
      if (!order.includes(name)) order.push(name);
    });
    return order;
  }

  /* ── Field inputs ──────────────────────────────────────────────────────── */

  function makeInput(type, value, placeholder) {
    const input = document.createElement("input");
    input.type = type;
    input.value = value || "";
    if (placeholder) input.placeholder = placeholder;
    return input;
  }

  function renderField(field, value, setValue, lookups) {
    const wrap = document.createElement("div");
    wrap.className = "form-field";

    const label = document.createElement("label");
    label.textContent = field.label || humanize(field.name);
    if (field.required) {
      const star = document.createElement("span");
      star.className = "req-star";
      star.textContent = " *";
      label.appendChild(star);
    }
    wrap.appendChild(label);

    let control;
    const type = field.type || "text";

    if (type === "bool") {
      control = document.createElement("select");
      const blank = document.createElement("option");
      blank.value = "";
      blank.textContent = "— not set —";
      control.appendChild(blank);
      [
        ["true", "Yes"],
        ["false", "No"],
      ].forEach(([val, text]) => {
        const option = document.createElement("option");
        option.value = val;
        option.textContent = text;
        control.appendChild(option);
      });
      control.value = value === undefined ? "" : String(value);
      control.addEventListener("change", () => setValue(control.value));
    } else if (type === "select") {
      control = document.createElement("select");
      if (!field.required) {
        const blank = document.createElement("option");
        blank.value = "";
        blank.textContent = "— not set —";
        control.appendChild(blank);
      }
      (field.options || []).forEach((option) => {
        const item = document.createElement("option");
        item.value = option;
        item.textContent = option;
        control.appendChild(item);
      });
      control.value = value || "";
      control.addEventListener("change", () => setValue(control.value));
    } else if (type === "lookup" || type === "multilookup") {
      const options = lookups && field.lookup ? lookups[field.lookup] : null;
      const valueField = field.valueField || "id";
      if (options && options.length) {
        control = document.createElement("select");
        if (type === "multilookup") control.multiple = true;
        else {
          const blank = document.createElement("option");
          blank.value = "";
          blank.textContent = "— select —";
          control.appendChild(blank);
        }
        options.forEach((option) => {
          const item = document.createElement("option");
          item.value = String(option.raw[valueField]);
          item.textContent = option.label;
          control.appendChild(item);
        });
        if (type === "multilookup") {
          const selected = Array.isArray(value) ? value.map(String) : [];
          Array.from(control.options).forEach((option) => {
            option.selected = selected.includes(option.value);
          });
          control.addEventListener("change", () =>
            setValue(Array.from(control.selectedOptions).map((option) => option.value)),
          );
        } else {
          control.value = value === undefined ? "" : String(value);
          control.addEventListener("change", () => setValue(control.value));
        }
      } else {
        control = makeInput("text", Array.isArray(value) ? value.join(",") : value, "load reference data for a dropdown");
        control.addEventListener("input", () => {
          if (type === "multilookup") {
            setValue(
              control.value
                .split(",")
                .map((part) => part.trim())
                .filter(Boolean),
            );
          } else {
            setValue(control.value);
          }
        });
      }
    } else {
      const inputTypes = { int: "number", float: "number", date: "date", time: "time", datetime: "datetime-local", email: "email", password: "password" };
      control = makeInput(inputTypes[type] || "text", value, field.placeholder);
      if (type === "int") control.step = "1";
      if (type === "float") control.step = "any";
      if (field.suggest && field.suggest.length) {
        const listId = `suggest-${field.name}-${Math.random().toString(36).slice(2, 7)}`;
        const list = document.createElement("datalist");
        list.id = listId;
        field.suggest.forEach((suggestion) => {
          const option = document.createElement("option");
          option.value = suggestion;
          list.appendChild(option);
        });
        control.setAttribute("list", listId);
        wrap.appendChild(list);
      }
      control.addEventListener("input", () => setValue(control.value));
    }

    wrap.appendChild(control);
    if (field.help) {
      const help = document.createElement("div");
      help.className = "form-help";
      help.textContent = field.help;
      wrap.appendChild(help);
    }
    return wrap;
  }

  /* ── Field groups ──────────────────────────────────────────────────────── */

  function renderSection(title, fields, values, setValue, lookups, open) {
    const details = document.createElement("details");
    details.className = "form-section";
    if (open) details.open = true;
    const summary = document.createElement("summary");
    summary.textContent = title;
    details.appendChild(summary);
    const grid = document.createElement("div");
    grid.className = "form-grid";
    fields.forEach((field) => {
      grid.appendChild(renderField(field, values[field.name], (val) => setValue(field.name, val), lookups));
    });
    details.appendChild(grid);
    return details;
  }

  function renderRows(container, ep, state, onChange, lookups) {
    const body = ep.body || {};
    const isStrings = body.shape === "string-array";
    const fields = body.itemFields || [];

    const list = document.createElement("div");
    list.className = "array-rows";
    container.appendChild(list);

    function redraw() {
      list.innerHTML = "";
      state.rows.forEach((row, index) => {
        const card = document.createElement("div");
        card.className = "array-row";

        const head = document.createElement("div");
        head.className = "array-row-head";
        const title = document.createElement("span");
        title.textContent = isStrings ? `${body.arrayLabel || "Item"} ${index + 1}` : `Record ${index + 1}`;
        head.appendChild(title);
        if (state.rows.length > 1) {
          const remove = document.createElement("button");
          remove.type = "button";
          remove.className = "btn btn-ghost btn-small";
          remove.textContent = "Remove";
          remove.addEventListener("click", () => {
            state.rows.splice(index, 1);
            onChange();
            redraw();
          });
          head.appendChild(remove);
        }
        card.appendChild(head);

        if (isStrings) {
          const wrap = document.createElement("div");
          wrap.className = "form-grid form-grid-single";
          wrap.appendChild(
            renderField(
              { name: "__value", label: "Event ID", placeholder: body.placeholder, type: "text" },
              row.__value,
              (val) => {
                row.__value = val;
                onChange();
              },
              lookups,
            ),
          );
          card.appendChild(wrap);
        } else {
          const wrap = document.createElement("div");
          wrap.className = "form-grid";
          fields.forEach((field) => {
            wrap.appendChild(
              renderField(field, row[field.name], (val) => {
                row[field.name] = val;
                onChange();
              }, lookups),
            );
          });
          card.appendChild(wrap);
        }
        list.appendChild(card);
      });
    }

    redraw();

    const add = document.createElement("button");
    add.type = "button";
    add.className = "btn btn-ghost btn-small";
    add.textContent = isStrings ? "Add event ID" : "Add record";
    add.addEventListener("click", () => {
      state.rows.push(isStrings ? { __value: "" } : emptyRow(fields));
      onChange();
      redraw();
    });
    container.appendChild(add);
  }

  function render(container, ep, state, onChange, lookups) {
    container.innerHTML = "";
    const body = ep.body || { shape: "none" };

    if (body.shape === "none") {
      const note = document.createElement("p");
      note.className = "hint";
      note.textContent = "This endpoint has no request body.";
      container.appendChild(note);
      return;
    }

    if (body.shape === "object") {
      const fields = body.fields || [];
      sectionOrder(fields).forEach((title, index) => {
        const group = fields.filter((field) => (field.section || "Details") === title);
        const setValue = (name, val) => {
          state.values[name] = val;
          onChange();
        };
        container.appendChild(renderSection(title, group, state.values, setValue, lookups, index === 0));
      });
      return;
    }

    if (body.arrayLabel) {
      const heading = document.createElement("div");
      heading.className = "array-heading";
      heading.textContent = body.arrayLabel;
      container.appendChild(heading);
    }
    renderRows(container, ep, state, onChange, lookups);
  }

  /* ── Build + validate ──────────────────────────────────────────────────── */

  function coerce(field, raw) {
    switch (field.type) {
      case "int": {
        const value = parseInt(raw, 10);
        return Number.isNaN(value) ? undefined : value;
      }
      case "float": {
        const value = Number(raw);
        return Number.isNaN(value) ? undefined : value;
      }
      case "bool":
        return raw === "true";
      default:
        return raw;
    }
  }

  function buildObject(fields, values) {
    const out = {};
    (fields || []).forEach((field) => {
      const raw = values[field.name];
      if (field.type === "multilookup") {
        const list = Array.isArray(raw) ? raw.map(Number).filter((n) => !Number.isNaN(n)) : [];
        if (list.length) out[field.name] = list;
        return;
      }
      if (raw === undefined || raw === null || raw === "") return;
      const value = coerce(field, raw);
      if (value !== undefined) out[field.name] = value;
    });
    return out;
  }

  function build(ep, state) {
    const body = ep.body || { shape: "none" };
    if (body.shape === "none") return undefined;
    if (body.shape === "object") return buildObject(body.fields, state.values);

    if (body.shape === "string-array") {
      const items = state.rows.map((row) => (row.__value || "").trim()).filter(Boolean);
      return items.length ? items : undefined;
    }

    const rows = state.rows.map((row) => buildObject(body.itemFields, row)).filter((row) => Object.keys(row).length);
    if (!rows.length) return undefined;
    if (body.shape === "object-array") return { [body.arrayKey || "records"]: rows };
    return rows;
  }

  function validate(ep, state) {
    const body = ep.body || { shape: "none" };
    if (body.shape === "none") return [];
    const errors = [];

    if (body.shape === "object") {
      (body.fields || []).forEach((field) => {
        const raw = state.values[field.name];
        const empty = raw === undefined || raw === null || raw === "" || (Array.isArray(raw) && !raw.length);
        if (field.required && empty) errors.push(`${field.label || humanize(field.name)} is required`);
      });
      return errors;
    }

    if (body.shape === "string-array") {
      if (!state.rows.some((row) => (row.__value || "").trim())) errors.push("Add at least one event ID");
      return errors;
    }

    state.rows.forEach((row, index) => {
      (body.itemFields || []).forEach((field) => {
        if (!field.required) return;
        const raw = row[field.name];
        if (raw === undefined || raw === null || raw === "") {
          errors.push(`Record ${index + 1}: ${field.label || humanize(field.name)} is required`);
        }
      });
    });
    return errors;
  }

  window.ErpForm = { initState, render, build, validate };
})();
