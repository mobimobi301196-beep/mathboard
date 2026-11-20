package ua.mathboard.app

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.view.WindowManager
import android.webkit.RenderProcessGoneDetail
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import android.widget.Toast
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat

/**
 * Оболочка над веб-версией MathBoard. Вся логика доски остаётся на сервере и в index.html.
 * Ученик: открыл приложение — сразу в уроке.
 * Учитель: значок приложения (долгое нажатие) -> «Я учитель» -> ввёл ключ один раз, дальше он запоминается.
 */
class MainActivity : Activity() {
    private lateinit var web: WebView
    private val handler = Handler(Looper.getMainLooper())
    private val prefs by lazy { getSharedPreferences("mb", MODE_PRIVATE) }
    private val serverHost: String get() = Uri.parse(BuildConfig.SERVER_URL).host ?: ""
    private var current = ""
    private var offline = false
    private var lastBack = 0L

    private val retry = Runnable {
        offline = false
        if (current.isNotEmpty()) web.loadUrl(current)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        if (Build.VERSION.SDK_INT >= 28) {
            window.attributes.layoutInDisplayCutoutMode =
                WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES
        }
        WindowCompat.setDecorFitsSystemWindows(window, false)

        web = WebView(this)
        web.setBackgroundColor(Color.BLACK)
        web.overScrollMode = WebView.OVER_SCROLL_NEVER
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            mediaPlaybackRequiresUserGesture = false
            setSupportZoom(false)
            builtInZoomControls = false
        }
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(v: WebView, r: WebResourceRequest): Boolean {
                if (r.url.host == serverHost) return false
                startActivity(Intent(Intent.ACTION_VIEW, r.url)); return true
            }

            override fun onReceivedError(v: WebView, r: WebResourceRequest, e: WebResourceError) {
                if (r.isForMainFrame) showOffline()
            }

            override fun onPageFinished(v: WebView, url: String?) {
                if (!offline) handler.removeCallbacks(retry)
            }

            // если «упал» процесс отрисовки — просто пересоздаём экран
            override fun onRenderProcessGone(v: WebView, d: RenderProcessGoneDetail): Boolean {
                recreate(); return true
            }
        }
        setContentView(web)
        handle(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handle(intent)
    }

    private fun handle(i: Intent?) {
        val data = i?.data
        if (data != null && data.host == serverHost) {
            data.getQueryParameter("key")?.let { prefs.edit().putString("key", it).apply() }
        }
        open()
        if (i?.action == "ua.mathboard.TEACHER") askKey()
    }

    private fun url(): String {
        val key = prefs.getString("key", "") ?: ""
        return BuildConfig.SERVER_URL + "/" + if (key.isNotEmpty()) "?key=" + Uri.encode(key) else ""
    }

    private fun open() {
        val u = url()
        if (u == current && !offline) return
        current = u; offline = false
        handler.removeCallbacks(retry)
        web.loadUrl(u)
    }

    private fun askKey() {
        val input = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            hint = "Ключ учителя"
            setText(prefs.getString("key", ""))
        }
        AlertDialog.Builder(this)
            .setTitle("Режим учителя")
            .setView(input)
            .setPositiveButton("Войти") { _, _ ->
                prefs.edit().putString("key", input.text.toString().trim()).apply(); open()
            }
            .setNeutralButton("Я ученик") { _, _ ->
                prefs.edit().remove("key").apply(); open()
            }
            .setNegativeButton("Отмена", null)
            .show()
    }

    private fun showOffline() {
        offline = true
        val html = "<body style='background:#000;color:#8B93A7;font:18px sans-serif;display:flex;" +
            "align-items:center;justify-content:center;height:100vh;margin:0;text-align:center'>" +
            "<div>Нет связи с сервером.<br>Проверьте интернет — подключаюсь снова…</div></body>"
        web.loadDataWithBaseURL(null, html, "text/html", "utf-8", null)
        handler.removeCallbacks(retry)
        handler.postDelayed(retry, 3000)
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        val t = System.currentTimeMillis()
        if (t - lastBack < 2000) super.onBackPressed()
        else { lastBack = t; Toast.makeText(this, "Нажмите «Назад» ещё раз, чтобы выйти", Toast.LENGTH_SHORT).show() }
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) WindowInsetsControllerCompat(window, window.decorView).apply {
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            hide(WindowInsetsCompat.Type.systemBars())
        }
    }

    override fun onResume() { super.onResume(); web.onResume() }
    override fun onPause() { web.onPause(); super.onPause() }
    override fun onDestroy() { handler.removeCallbacks(retry); web.destroy(); super.onDestroy() }
}
