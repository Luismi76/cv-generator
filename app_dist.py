import os, json
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("CVTOOL_DATA_DIR", os.path.join(APP_DIR, "data"))
OUT_DIR  = os.path.join(DATA_DIR, "output")
TEMPLATES_DIR = os.path.join(APP_DIR, "render_templates")

# AÑADIR ESTAS LÍNEAS DE DEPURACIÓN
print(f"APP_DIR: {APP_DIR}")
print(f"DATA_DIR: {DATA_DIR}")
print(f"Creando carpetas...")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

print(f"Carpetas creadas. ¿Existe DATA_DIR? {os.path.exists(DATA_DIR)}")
# fin de la depuración

# os.makedirs(DATA_DIR, exist_ok=True); os.makedirs(OUT_DIR, exist_ok=True)

app = Flask(__name__, template_folder=os.path.join(APP_DIR, "templates"), static_folder=os.path.join(APP_DIR, "static"))

def load_cv():
    path = os.path.join(DATA_DIR, "cv.json")
    if not os.path.exists(path):
        return {"contact":{"links":[]}, "summary":"", "skills":[], "experience":[], "projects":[], "education":[], "courses":[], "otros":[]}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_cv(cv): 
    with open(os.path.join(DATA_DIR, "cv.json"), "w", encoding="utf-8") as f: 
        json.dump(cv, f, ensure_ascii=False, indent=2)

def load_templates():
    """Carga las plantillas de CV guardadas"""
    path = os.path.join(DATA_DIR, "templates.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_templates(templates):
    """Guarda las plantillas de CV"""
    with open(os.path.join(DATA_DIR, "templates.json"), "w", encoding="utf-8") as f:
        json.dump(templates, f, ensure_ascii=False, indent=2)

def _dedup_otros(cv_dict):
    otros = cv_dict.get("otros", []); seen=set(); cleaned=[]
    for o in otros:
        sig = ((o.get("title") or "").strip(), (o.get("institution") or o.get("company") or "").strip(), (o.get("periodo") or o.get("start") or "").strip())
        if sig not in seen: seen.add(sig); cleaned.append(o)
    cv_dict["otros"] = cleaned; return cv_dict

def filter_cv_by_selection(cv, selection):
    """Filtra el CV basándose en la selección y orden especificados"""
    filtered_cv = {
        "contact": cv.get("contact", {}),
        "summary": cv.get("summary", "") if selection.get("include_summary", True) else ""
    }
    
    # Secciones que se pueden filtrar y reordenar
    sections = ["skills", "experience", "projects", "education", "courses", "otros"]
    
    for section in sections:
        if section in selection and "selected" in selection[section]:
            # Obtener elementos seleccionados en el orden especificado
            original_items = cv.get(section, [])
            selected_indices = selection[section]["selected"]
            order = selection[section].get("order", list(range(len(selected_indices))))
            
            # Crear lista ordenada de elementos seleccionados
            selected_items = []
            for pos in order:
                if pos < len(selected_indices):
                    idx = selected_indices[pos]
                    if idx < len(original_items):
                        selected_items.append(original_items[idx])
            
            filtered_cv[section] = selected_items
        else:
            # Si no hay selección, incluir todos los elementos
            filtered_cv[section] = cv.get(section, [])
    
    return filtered_cv

from jinja2 import Environment, FileSystemLoader
def render_to_text(cv, fmt="md"):
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=False, trim_blocks=False, lstrip_blocks=False)
    tpl = env.get_template("cv.md.j2") if fmt=="md" else env.get_template("cv.txt.j2")
    return tpl.render(**cv)

# Rutas existentes (mantenidas igual)
@app.route("/")
def index():
    cv = load_cv(); return render_template("index.html", cv=cv, title="Inicio")

@app.route("/acerca")
def about():
    return render_template("about.html", title="Acerca de")

@app.route("/contact", methods=["GET","POST"])
def contact():
    cv = load_cv()
    if request.method=="POST":
        c = cv.get("contact", {})
        for k in ["name","title","location","email","phone"]:
            c[k] = request.form.get(k,"")
        links = request.form.get("links","").strip()
        c["links"] = [x.strip() for x in links.split(",")] if links else []
        cv["contact"]=c; save_cv(cv); return redirect(url_for("contact"))
    return render_template("contact.html", cv=cv, title="Contacto")

@app.route("/summary", methods=["GET","POST"])
def summary():
    cv = load_cv()
    if request.method=="POST":
        cv["summary"] = request.form.get("summary",""); save_cv(cv); return redirect(url_for("summary"))
    return render_template("summary.html", cv=cv, title="Resumen")

FIELDS = {
 "skills":["name","level","tags"],
 "experience":["title","company","location","start","end","description","tech"],
 "projects":["title","company","location","start","end","description","tech"],
 "education":["degree","institution","start","end","notes"],
 "courses":["name","issuer","date","hours","credential","tags"],
 "otros":["title","institution","start","end","periodo","description","tags"]
}

def _get_list(cv, section):
    if section not in cv: cv[section]=[]
    return cv[section]

@app.route("/<section>")
def list_items(section):
    cv = load_cv(); items=list(enumerate(_get_list(cv, section)))
    return render_template("list.html", section=section, items=items, title=section.capitalize())

@app.route("/<section>/add", methods=["GET","POST"])
def add_item(section):
    cv = load_cv(); item={}
    if request.method=="POST":
        for k in FIELDS.get(section, []):
            v = request.form.get(k,"").strip()
            if k in ("tags","tech"):
                item[k] = [x.strip() for x in v.split(",") if x.strip()]
            else:
                item[k] = v
        cv[section].append(item); save_cv(cv); return redirect(url_for("list_items", section=section))
    return render_template("edit_item.html", section=section, item=item, action="Añadir", title="Añadir")

@app.route("/<section>/edit/<int:idx>", methods=["GET","POST"])
def edit_item(section, idx):
    cv = load_cv(); lst=_get_list(cv, section)
    if idx<0 or idx>=len(lst): return redirect(url_for("list_items", section=section))
    if request.method=="POST":
        item = lst[idx]
        for k in FIELDS.get(section, []):
            v = request.form.get(k,"").strip()
            if k in ("tags","tech"):
                item[k] = [x.strip() for x in v.split(",") if x.strip()]
            else:
                item[k] = v
        save_cv(cv); return redirect(url_for("list_items", section=section))
    return render_template("edit_item.html", section=section, item=lst[idx], action="Editar", title="Editar")

@app.route("/<section>/delete/<int:idx>")
def delete_item(section, idx):
    cv = load_cv(); lst=_get_list(cv, section)
    if 0<=idx<len(lst): lst.pop(idx); save_cv(cv)
    return redirect(url_for("list_items", section=section))

# NUEVAS RUTAS PARA SELECCIÓN Y PERSONALIZACIÓN

@app.route("/personalizar")
def customize():
    """Página principal para personalizar el CV"""
    cv = load_cv()
    templates = load_templates()
    return render_template("customize.html", cv=cv, templates=templates, title="Personalizar CV")

@app.route("/personalizar/plantilla/<template_name>")
def load_template(template_name):
    """Carga una plantilla guardada"""
    templates = load_templates()
    if template_name in templates:
        return jsonify(templates[template_name])
    return jsonify({"error": "Plantilla no encontrada"}), 404

@app.route("/personalizar/guardar", methods=["POST"])
def save_template():
    """Guarda una plantilla de selección"""
    data = request.get_json()
    template_name = data.get("name", "")
    selection = data.get("selection", {})
    
    if not template_name:
        return jsonify({"error": "Nombre de plantilla requerido"}), 400
    
    templates = load_templates()
    templates[template_name] = {
        "name": template_name,
        "description": data.get("description", ""),
        "selection": selection,
        "created": data.get("created", "")
    }
    save_templates(templates)
    
    return jsonify({"success": True, "message": "Plantilla guardada correctamente"})

@app.route("/personalizar/eliminar/<template_name>", methods=["POST"])
def delete_template(template_name):
    """Elimina una plantilla guardada"""
    templates = load_templates()
    if template_name in templates:
        del templates[template_name]
        save_templates(templates)
        return jsonify({"success": True, "message": "Plantilla eliminada"})
    return jsonify({"error": "Plantilla no encontrada"}), 404

@app.route("/preview")
def preview():
    cv = _dedup_otros(load_cv()); fmt = request.args.get("fmt","md")
    content = render_to_text(cv, fmt=fmt)
    return render_template("preview.html", content=content, title="Vista previa")

@app.route("/preview/personalizada", methods=["POST"])
def preview_custom():
    """Vista previa con selección personalizada"""
    data = request.get_json()
    selection = data.get("selection", {})
    fmt = data.get("fmt", "md")
    
    cv = _dedup_otros(load_cv())
    filtered_cv = filter_cv_by_selection(cv, selection)
    content = render_to_text(filtered_cv, fmt=fmt)
    
    return jsonify({"content": content})

@app.route("/generar", methods=["GET","POST"])
def generate():
    cv = _dedup_otros(load_cv()); fmt="md"; outname="CV"; outputs=[]
    if request.method=="POST":
        fmt = request.form.get("fmt","md")
        outname = request.form.get("outname","CV")
        
        # Comprobar si hay selección personalizada
        selection_data = request.form.get("selection_data")
        if selection_data:
            try:
                selection = json.loads(selection_data)
                cv = filter_cv_by_selection(cv, selection)
            except:
                pass  # Si hay error, usar CV completo
        
        content = render_to_text(cv, fmt=fmt)
        ext = ".md" if fmt=="md" else ".txt"
        outpath = os.path.join(OUT_DIR, f"{outname}{ext}")
        with open(outpath,"w",encoding="utf-8") as f: f.write(content)
        outputs.append(os.path.basename(outpath))
    return render_template("generate.html", fmt=fmt, outname=outname, outputs=outputs, title="Generar")

@app.route("/generar/personalizado", methods=["POST"])
def generate_custom():
    """Genera CV con selección personalizada"""
    data = request.get_json()
    selection = data.get("selection", {})
    fmt = data.get("fmt", "md")
    outname = data.get("outname", "CV_personalizado")
    
    cv = _dedup_otros(load_cv())
    filtered_cv = filter_cv_by_selection(cv, selection)
    content = render_to_text(filtered_cv, fmt=fmt)
    
    ext = ".md" if fmt == "md" else ".txt"
    outpath = os.path.join(OUT_DIR, f"{outname}{ext}")
    with open(outpath, "w", encoding="utf-8") as f:
        f.write(content)
    
    return jsonify({
        "success": True,
        "filename": f"{outname}{ext}",
        "message": "CV generado correctamente"
    })

@app.route("/download/<path:path>")
def download(path):
    return send_from_directory(OUT_DIR, path, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)