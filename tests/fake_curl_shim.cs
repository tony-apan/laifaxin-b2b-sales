using System;
using System.Diagnostics;
using System.Text;

// Windows 上 CreateProcess 只解析 .exe；本 shim 把 curl 调用转发给 fake_curl.py。
class FakeCurlShim {
    static string Q(string s) {
        var sb = new StringBuilder();
        sb.Append((char)34);
        int bs = 0;
        foreach (char c in s) {
            if (c == (char)92) { sb.Append(c); bs++; }
            else if (c == (char)34) { sb.Append((char)92, bs + 1); sb.Append((char)34); bs = 0; }
            else { sb.Append(c); bs = 0; }
        }
        sb.Append((char)92, bs);
        sb.Append((char)34);
        return sb.ToString();
    }

    static int Main(string[] args) {
        string dir = AppDomain.CurrentDomain.BaseDirectory;
        string py = Environment.GetEnvironmentVariable("LFX_FAKE_PYTHON");
        if (String.IsNullOrEmpty(py)) py = "py";
        var sb = new StringBuilder();
        sb.Append(Q(System.IO.Path.Combine(dir, "fake_curl.py")));
        foreach (var a in args) { sb.Append(' '); sb.Append(Q(a)); }
        var psi = new ProcessStartInfo();
        psi.FileName = py;
        psi.Arguments = sb.ToString();
        psi.UseShellExecute = false;
        var p = Process.Start(psi);
        p.WaitForExit();
        return p.ExitCode;
    }
}
