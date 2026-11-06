const { app, BrowserWindow, ipcMain, shell, Menu, dialog } = require('electron')
const { spawn } = require('child_process')
const path = require('path')
const fs = require('fs')
const http = require('http')
const net = require('net')

const ROOT = path.join(__dirname, '..')
const PYTHON_CANDIDATES = [
  process.env.NEO_PYTHON,
  path.join(ROOT, '.runtime', 'python', 'python.exe'),
  path.join(ROOT, '.runtime', 'python', 'python'),
  'python',
].filter(Boolean)

let mainWindow = null
let backend = null
let backendPort = null
let backendReady = false
let closing = false
let allowClose = false
let closeTimer = null

function log(...args) {
  console.log('[neo]', ...args)
}

function isPortFree(port) {
  return new Promise((resolve) => {
    const server = net.createServer()
    server.once('error', () => resolve(false))
    server.once('listening', () => server.close(() => resolve(true)))
    server.listen(port, '127.0.0.1')
  })
}

async function pickPort(start) {
  for (let port = start; port < start + 30; port += 1) {
    if (await isPortFree(port)) return port
  }
  return start
}

function resolvePython() {
  for (const candidate of PYTHON_CANDIDATES) {
    if (candidate === 'python') return candidate
    try {
      if (fs.existsSync(candidate)) return candidate
    } catch (error) {
      /* ignore */
    }
  }
  return 'python'
}

function startBackend(port) {
  const python = resolvePython()
  const script = path.join(ROOT, 'backend', 'main.py')
  if (!fs.existsSync(script)) {
    log('未找到后端入口', script)
    return null
  }
  backend = spawn(python, [script], {
    cwd: ROOT,
    env: {
      ...process.env,
      NEO_PORT: String(port),
      PYTHONPATH: path.join(ROOT, 'backend'),
      PYTHONIOENCODING: 'utf-8',
      PYTHONUTF8: '1',
      PYTHONLEGACYWINDOWSSTDIO: '0',
    },
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  backend.stdout.on('data', (chunk) => {
    const text = chunk.toString('utf-8').trimEnd()
    if (text) log(text)
    forwardLog(text, 'stdout')
  })
  backend.stderr.on('data', (chunk) => {
    const text = chunk.toString('utf-8').trimEnd()
    if (text) log(text)
    forwardLog(text, 'stderr')
  })
  backend.on('exit', (code, signal) => {
    log(`后端进程退出 code=${code} signal=${signal}`)
    backendReady = false
    backend = null
    forwardLog(`后端进程已退出（code=${code}）`, 'exit')
  })
  return backend
}

function forwardLog(line, stream) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('backend:log', { line, stream, ts: Date.now() })
  }
}

function waitForBackend(port, attempts = 100) {
  return new Promise((resolve, reject) => {
    let remaining = attempts
    const probe = () => {
      const request = http.get(
        { host: '127.0.0.1', port, path: '/api/health', timeout: 900 },
        (response) => {
          response.resume()
          if (response.statusCode === 200) {
            backendReady = true
            resolve(true)
          } else if (remaining-- > 0) {
            setTimeout(probe, 250)
          } else {
            reject(new Error('后端健康检查失败'))
          }
        }
      )
      request.on('timeout', () => request.destroy())
      request.on('error', () => {
        if (remaining-- > 0) setTimeout(probe, 250)
        else reject(new Error('后端未能在预期时间内启动'))
      })
    }
    probe()
  })
}

async function createWindow(port) {
  mainWindow = new BrowserWindow({
    width: 1240,
    height: 780,
    minWidth: 960,
    minHeight: 640,
    show: false,
    frame: false,
    icon: path.join(ROOT, 'icon.jpg'),
    backgroundColor: '#090d0a',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      spellcheck: false,
      additionalArguments: [`--neo-port=${port}`],
    },
  })

  mainWindow.once('ready-to-show', () => mainWindow.show())

  const sendMaximize = () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('window:maximized', mainWindow.isMaximized())
    }
  }
  mainWindow.on('maximize', sendMaximize)
  mainWindow.on('unmaximize', sendMaximize)

  mainWindow.on('close', async (event) => {
    if (allowClose) return
    event.preventDefault()
    if (closing) return
    closing = true
    let image = null
    try {
      const capture = await mainWindow.webContents.capturePage()
      if (capture && !capture.isEmpty()) image = capture.toDataURL()
    } catch (error) {
      log('窗口截图失败，使用纯粒子动画', error.message)
    }
    mainWindow.webContents.send('app:request-close', { image })
    closeTimer = setTimeout(() => {
      allowClose = true
      if (mainWindow && !mainWindow.isDestroyed()) mainWindow.destroy()
    }, 6000)
  })

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  await mainWindow.loadFile(path.join(ROOT, 'frontend', 'dist', 'index.html'))
}

function setupIpc() {
  ipcMain.handle('app:info', () => ({
    name: app.getName(),
    version: app.getVersion(),
    platform: process.platform,
    apiBase: `http://127.0.0.1:${backendPort}`,
    backendReady,
  }))

  ipcMain.handle('window:minimize', () => mainWindow && mainWindow.minimize())
  ipcMain.handle('window:maximize', () => {
    if (!mainWindow) return false
    if (mainWindow.isMaximized()) mainWindow.unmaximize()
    else mainWindow.maximize()
    return mainWindow.isMaximized()
  })
  ipcMain.handle('window:close', () => mainWindow && mainWindow.close())
  ipcMain.handle('window:is-maximized', () => Boolean(mainWindow && mainWindow.isMaximized()))
  ipcMain.handle('shell:open-external', (_event, url) => {
    if (typeof url === 'string' && /^https?:/i.test(url)) return shell.openExternal(url)
    return null
  })

  ipcMain.handle('dialog:pick-directory', async (_event, title) => {
    if (!mainWindow) return null
    const result = await dialog.showOpenDialog(mainWindow, {
      title: typeof title === 'string' && title ? title : '选择文件夹',
      properties: ['openDirectory', 'createDirectory'],
    })
    if (result.canceled || !result.filePaths.length) return null
    return result.filePaths[0]
  })

  ipcMain.handle('dialog:pick-file', async (_event, payload) => {
    if (!mainWindow) return null
    const options = payload && typeof payload === 'object' ? payload : {}
    const result = await dialog.showOpenDialog(mainWindow, {
      title: options.title || '选择文件',
      properties: ['openFile'],
      filters: Array.isArray(options.filters) ? options.filters : [{ name: '整合包', extensions: ['mrpack', 'zip'] }],
    })
    if (result.canceled || !result.filePaths.length) return null
    return result.filePaths[0]
  })

  ipcMain.on('app:close-ready', () => {
    if (!closing) return
    if (closeTimer) {
      clearTimeout(closeTimer)
      closeTimer = null
    }
    allowClose = true
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.destroy()
  })
}

const singleInstanceLock = app.requestSingleInstanceLock()
if (!singleInstanceLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.focus()
    }
  })

  app.whenReady().then(async () => {
    if (process.platform === 'win32') app.setAppUserModelId('com.neocatcraft.launcher')
    Menu.setApplicationMenu(null)
    backendPort = await pickPort(Number(process.env.NEO_PORT || 47821))
    log(`后端端口: ${backendPort}`)
    startBackend(backendPort)
    setupIpc()
    await createWindow(backendPort)
    waitForBackend(backendPort)
      .then(() => {
        log('后端已就绪')
        forwardLog('后端已就绪', 'system')
      })
      .catch((error) => {
        log(error.message)
        forwardLog(error.message, 'error')
      })
  })

  app.on('window-all-closed', () => {
    app.quit()
  })

  app.on('before-quit', () => {
    if (closeTimer) clearTimeout(closeTimer)
    if (backend && backend.pid) {
      try {
        backend.kill()
      } catch (error) {
        log('终止后端失败', error.message)
      }
    }
  })
}
