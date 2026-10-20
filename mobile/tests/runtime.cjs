const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function loadSource(relativePath, globals = {}, modules = {}) {
  const filename = path.join(__dirname, '..', relativePath);
  const source = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    fileName: filename,
  }).outputText;
  const module = { exports: {} };
  const context = vm.createContext({ module, exports: module.exports,
    require: (name) => name in modules ? modules[name] : require(name),
    console, setTimeout, clearTimeout, AbortController, Headers, Response,
    process: { env: { EXPO_PUBLIC_API_BASE_URL: 'https://api.example.test' } },
    __DEV__: false, ...globals });
  vm.runInContext(source, context, { filename });
  return module.exports;
}
module.exports = { loadSource };
