/* Point and Click Museum · tiny rule engine shared by the data-driven minigames.
   A rule (see data/minigames/*.json):
     { "verb": "open" | ["open","use"], "noun": "hatch" | ["hatch", null], "item": "key",
       "room": "basement", "arg": "1976" | "none", "if": ["flag", "!flag", "has:item", "room:id", "count:n>=2"],
       "do": ["set:f", "unset:f", "give:i", "remove:i", "drop:i", "inc:c", "award:key", "sound:open", "look", "win"],
       "say": "text" | "sayList": ["...", "..."] + "counter": "c" }
   The first matching rule wins. */
"use strict";
PCM.Rules = (() => {
  function cond(c, S) {
    const neg = c[0] === "!", body = neg ? c.slice(1) : c;
    let r;
    if (body.startsWith("has:")) r = S.inv.includes(body.slice(4));
    else if (body.startsWith("room:")) r = S.room === body.slice(5);
    else if (body.startsWith("count:")) {
      const m = /^count:(\w+)(>=|<=|==|>|<)(\d+)$/.exec(body); const v = (S.counters[m[1]] || 0), n = +m[3];
      r = { ">=": v >= n, "<=": v <= n, "==": v === n, ">": v > n, "<": v < n }[m[2]];
    } else r = !!S.flags[body];
    return neg ? !r : r;
  }
  const all = (list, S) => !list || list.every(c => cond(c, S));

  function matches(rule, q, S) {
    if (![].concat(rule.verb).includes(q.verb)) return false;
    if ("noun" in rule) {
      const ns = [].concat(rule.noun);
      if (!ns.includes(q.noun == null ? null : q.noun) && !(q.noun2 != null && ns.includes(q.noun2))) return false;
    }
    if ("item" in rule) { if (rule.item !== q.item) return false; } else if (q.item) return false;
    if (rule.room && rule.room !== S.room) return false;
    if ("arg" in rule) { if (rule.arg === "none" ? q.arg != null : rule.arg !== q.arg) return false; }
    return all(rule.if, S);
  }
  function find(rules, q, S, symmetric) {
    let r = rules.find(x => matches(x, q, S));
    if (!r && symmetric && q.item && q.noun) r = rules.find(x => matches(x, Object.assign({}, q, { item: q.noun, noun: q.item }), S));
    return r || null;
  }
  function text(rule, S) {
    if (rule.sayList) { const i = Math.min(S.counters[rule.counter] || 0, rule.sayList.length - 1); return rule.sayList[i]; }
    return rule.say || "";
  }
  /* hooks: { give(i), remove(i), drop(i), look(), win(), award(k), sound(s) } */
  function apply(effects, S, hooks) {
    (effects || []).forEach(e => {
      const k = e.indexOf(":"), op = k < 0 ? e : e.slice(0, k), arg = k < 0 ? "" : e.slice(k + 1);
      switch (op) {
        case "set": S.flags[arg] = true; break;
        case "unset": delete S.flags[arg]; break;
        case "inc": S.counters[arg] = (S.counters[arg] || 0) + 1; break;
        case "give": if (!S.inv.includes(arg)) S.inv.push(arg); if (hooks.give) hooks.give(arg); break;
        case "remove": S.inv = S.inv.filter(i => i !== arg); if (hooks.remove) hooks.remove(arg); break;
        case "drop": S.inv = S.inv.filter(i => i !== arg); if (hooks.drop) hooks.drop(arg); break;
        default: if (hooks[op]) hooks[op](arg);
      }
    });
  }
  const fragments = (list, S) => (list || []).filter(f => all(f.if, S)).map(f => f.text).join(" ");
  return { cond, all, matches, find, text, apply, fragments };
})();
