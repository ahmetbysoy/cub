"use strict";
/*
 * CubeCraft mini mod ajanı — prototip
 * frida-il2cpp-bridge'in dist/index.js dosyasından SONRA yüklenir; `Il2Cpp` globali hazırdır.
 * Sunucu (server.py) bu ajanı yükler ve rpc.exports üzerinden konuşur.
 */

const watches = new Map();
let seq = 0;

function log(msg, level) {
    send({ type: "log", level: level || "info", msg: String(msg), ts: Date.now() });
}

function jsonable(value) {
    try {
        return JSON.parse(JSON.stringify(value));
    } catch (_) {
        return String(value);
    }
}

function typeNameOf(method) {
    try {
        return method.returnType.name;
    } catch (_) {
        return "?";
    }
}

function readReturn(retval, typeName) {
    const n = (typeName || "").toLowerCase();
    try {
        if (n.includes("boolean")) return retval.toInt32() !== 0;
        if (n.includes("int64") || n.includes("uint64") || n.includes("long")) return retval.toInt64().toString();
        if (n.includes("single") || n.includes("float")) return retval.readFloat();
        if (n.includes("double")) return retval.readDouble();
        return retval.toInt32();
    } catch (e) {
        return String(retval);
    }
}

function findClass(spec) {
    for (const assembly of Il2Cpp.domain.assemblies) {
        if (spec.assembly && assembly.name !== spec.assembly) continue;
        for (const klass of assembly.image.classes) {
            if (klass.name !== spec.name) continue;
            const ns = spec.namespace === undefined || spec.namespace === null ? spec.namespace : spec.namespace;
            if (ns !== undefined && ns !== null && (klass.namespace || "") !== ns) continue;
            return { assembly: assembly, klass: klass };
        }
    }
    return null;
}

function resolveMethod(spec) {
    const found = findClass(spec);
    if (!found) {
        throw new Error("sınıf bulunamadı: " + ((spec.namespace ? spec.namespace + "." : "") + spec.name));
    }
    const m = (spec.paramCount === undefined || spec.paramCount === null)
        ? found.klass.method(spec.method)
        : found.klass.method(spec.method, spec.paramCount);
    return { found: found, method: m };
}

function toArg(value) {
    return typeof value === "string" ? Il2Cpp.String.from(value) : value;
}

function findSingleton(klass, preferred) {
    const names = preferred ? [preferred] : ["get_Instance", "get_instance", "get_Singleton", "get_singleton", "get_Current", "get_current"];
    for (const name of names) {
        try {
            const getter = klass.tryMethod(name, 0);
            if (getter) return { getter: name, value: getter.invoke() };
        } catch (_) { /* sıradakini dene */ }
    }
    return null;
}

Il2Cpp.perform(() => {
    log("IL2CPP hazır · Unity " + Il2Cpp.unityVersion + " · " + Il2Cpp.domain.assemblies.length + " assembly");
});

rpc.exports = {
    ping() {
        return Il2Cpp.perform(() => {
            let classes = 0;
            for (const a of Il2Cpp.domain.assemblies) classes += a.image.classCount;
            return { ok: true, unityVersion: Il2Cpp.unityVersion, assemblies: Il2Cpp.domain.assemblies.length, classes: classes };
        });
    },

    searchClasses(term, limit) {
        term = String(term || "").toLowerCase();
        limit = limit || 100;
        return Il2Cpp.perform(() => {
            const out = [];
            for (const assembly of Il2Cpp.domain.assemblies) {
                for (const klass of assembly.image.classes) {
                    const full = ((klass.namespace || "") + "." + klass.name).toLowerCase();
                    if (term && full.indexOf(term) === -1) continue;
                    out.push({
                        assembly: assembly.name,
                        namespace: klass.namespace || "",
                        name: klass.name,
                        fullName: klass.fullName,
                        methods: klass.methods.length,
                        fields: klass.fields.length
                    });
                    if (out.length >= limit) return out;
                }
            }
            return out;
        });
    },

    listMethods(assembly, namespace, name, limit) {
        limit = limit || 250;
        return Il2Cpp.perform(() => {
            const found = findClass({ assembly: assembly, namespace: namespace, name: name });
            if (!found) throw new Error("sınıf bulunamadı");
            return found.klass.methods.slice(0, limit).map((m) => ({
                name: m.name,
                parameterCount: m.parameterCount,
                isStatic: m.isStatic,
                returnType: typeNameOf(m),
                rva: m.relativeVirtualAddress.toString(),
                va: m.virtualAddress.toString(),
                parameters: (m.parameters || []).map((p) => {
                    try { return p.type.name + " " + p.name; } catch (_) { return "?"; }
                })
            }));
        });
    },

    listFields(assembly, namespace, name, limit) {
        limit = limit || 250;
        return Il2Cpp.perform(() => {
            const found = findClass({ assembly: assembly, namespace: namespace, name: name });
            if (!found) throw new Error("sınıf bulunamadı");
            return found.klass.fields.slice(0, limit).map((f) => ({
                name: f.name,
                type: (function () { try { return f.type.name; } catch (_) { return "?"; } })(),
                isStatic: f.isStatic,
                offset: (function () { try { return f.offset.toString(); } catch (_) { return "?"; } })()
            }));
        });
    },

    readField(spec) {
        return Il2Cpp.perform(() => {
            const found = findClass(spec);
            if (!found) throw new Error("sınıf bulunamadı");
            const field = found.klass.fields.filter((f) => f.name === spec.field)[0];
            if (!field) throw new Error("alan bulunamadı: " + spec.field);
            if (field.isStatic) return jsonable({ value: String(field.value) });
            const singleton = findSingleton(found.klass, spec.singletonGetter);
            if (!singleton) throw new Error("örnek (singleton) bulunamadı — statik alan değil");
            return jsonable({ value: String(singleton.value.field(spec.field).value) });
        });
    },

    writeField(spec) {
        return Il2Cpp.perform(() => {
            const found = findClass(spec);
            if (!found) throw new Error("sınıf bulunamadı");
            const field = found.klass.fields.filter((f) => f.name === spec.field)[0];
            if (!field) throw new Error("alan bulunamadı: " + spec.field);
            const value = typeof spec.value === "number" ? spec.value : Number(spec.value);
            if (field.isStatic) {
                field.value = value;
                return { ok: true, scope: "static", value: String(field.value) };
            }
            const singleton = findSingleton(found.klass, spec.singletonGetter);
            if (!singleton) throw new Error("örnek (singleton) bulunamadı");
            singleton.value.field(spec.field).value = value;
            return { ok: true, scope: "instance(" + singleton.getter + ")", value: String(singleton.value.field(spec.field).value) };
        });
    },

    invoke(spec) {
        return Il2Cpp.perform(() => {
            const args = (spec.args || []).map(toArg);
            if (spec.onInstance) {
                const found = findClass(spec);
                if (!found) throw new Error("sınıf bulunamadı");
                const singleton = findSingleton(found.klass, spec.singletonGetter);
                if (!singleton) throw new Error("örnek (singleton) bulunamadı");
                const bound = singleton.value.method(spec.method, spec.paramCount);
                return jsonable({ result: String(bound.invoke.apply(bound, args)) });
            }
            const resolved = resolveMethod(spec);
            const unbound = resolved.method;
            return jsonable({ result: String(unbound.invoke.apply(unbound, args)) });
        });
    },

    watch(spec) {
        return Il2Cpp.perform(() => {
            const resolved = resolveMethod(spec);
            const method = resolved.method;
            const id = "w" + (++seq);
            const typeName = typeNameOf(method);
            const label = (spec.namespace ? spec.namespace + "." : "") + spec.name + "." + spec.method;

            if (spec.mode === "const" || spec.mode === "noop") {
                const fixed = spec.mode === "noop" ? undefined : toArg(spec.value);
                method.implementation = function () {
                    if (spec.mode === "noop") return undefined;
                    return fixed;
                };
                watches.set(id, { id: id, mode: spec.mode, label: label, kind: "implementation" });
                log("Mod kuruldu (" + spec.mode + "): " + label + " → " + JSON.stringify(spec.value));
                return { ok: true, id: id, mode: spec.mode, label: label, returnType: typeName };
            }

            const address = method.virtualAddress;
            const listener = Interceptor.attach(address, {
                onEnter(args) {
                    if (spec.mode === "log") {
                        log("→ " + label + " (" + method.parameterCount + " parametre)");
                    }
                },
                onLeave(retval) {
                    const value = readReturn(retval, typeName);
                    if (spec.mode === "multiply") {
                        const factor = Number(spec.factor || 1);
                        if (typeof value === "number") {
                            const scaled = Math.trunc(value * factor);
                            retval.replace(scaled);
                            log("×" + factor + " " + label + ": " + value + " → " + scaled);
                        }
                    } else {
                        log("← " + label + " = " + value + "  (" + typeName + ")");
                    }
                }
            });
            watches.set(id, { id: id, mode: spec.mode, label: label, kind: "interceptor", listener: listener });
            log("İzleme kuruldu (" + spec.mode + "): " + label);
            return { ok: true, id: id, mode: spec.mode, label: label, returnType: typeName };
        });
    },

    unwatch(id) {
        return Il2Cpp.perform(() => {
            const w = watches.get(id);
            if (!w) throw new Error("kayıt yok: " + id);
            if (w.kind === "interceptor") w.listener.detach();
            watches.delete(id);
            log("Mod kaldırıldı: " + w.label);
            return { ok: true, id: id };
        });
    },

    unwatchAll() {
        return Il2Cpp.perform(() => {
            let n = 0;
            watches.forEach((w) => {
                if (w.kind === "interceptor") w.listener.detach();
                n++;
            });
            watches.clear();
            log(n + " mod kaldırıldı");
            return { ok: true, removed: n };
        });
    },

    listWatches() {
        const out = [];
        watches.forEach((w) => out.push({ id: w.id, mode: w.mode, label: w.label }));
        return out;
    }
};
