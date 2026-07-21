$env:PATH = 'C:\Users\anilk\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;' + $env:PATH
Set-Location 'D:\algo\frontend'
& 'C:\Users\anilk\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' 'C:\Users\anilk\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\pnpm\bin\pnpm.cjs' run dev --host 127.0.0.1 *>> 'D:\algo\frontend_dev_runtime.log'
