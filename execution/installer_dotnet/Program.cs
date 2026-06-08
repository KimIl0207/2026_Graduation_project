using System.Reflection;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace ADAMCaptureSetup;

internal static class Program
{
    private const string AppName = "ADAM Capture";

    [STAThread]
    private static void Main()
    {
        try
        {
            var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            var appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
            var desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            var installDir = Path.Combine(localAppData, "ADAMCapture");
            var startMenuDir = Path.Combine(appData, "Microsoft", "Windows", "Start Menu", "Programs", "ADAM");

            Directory.CreateDirectory(installDir);
            Directory.CreateDirectory(startMenuDir);
            ExtractPayload(installDir);

            var pythonw = FindExecutable("pythonw.exe") ?? FindExecutable("python.exe");
            if (pythonw is null)
            {
                MessageBox.Show(
                    "Python was not found. Install Python and Pillow, then run ADAM Capture again.",
                    AppName,
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Warning);
                return;
            }

            var appScript = Path.Combine(installDir, "adam_capture.pyw");
            CreateShortcut(Path.Combine(desktop, "ADAM Capture.lnk"), pythonw, $"\"{appScript}\"", installDir);
            CreateShortcut(Path.Combine(startMenuDir, "ADAM Capture.lnk"), pythonw, $"\"{appScript}\"", installDir);
            WriteUninstaller(installDir, desktop, startMenuDir);

            MessageBox.Show(
                "ADAM Capture installed.\nDesktop and Start Menu shortcuts were created.",
                AppName,
                MessageBoxButtons.OK,
                MessageBoxIcon.Information);
        }
        catch (Exception ex)
        {
            MessageBox.Show(ex.Message, $"{AppName} setup failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private static void ExtractPayload(string installDir)
    {
        var assembly = Assembly.GetExecutingAssembly();
        foreach (var resourceName in assembly.GetManifestResourceNames().Where(name => name.StartsWith("payload.")))
        {
            var fileName = resourceName["payload.".Length..];
            if (fileName.StartsWith("assets."))
            {
                Directory.CreateDirectory(Path.Combine(installDir, "assets"));
                fileName = Path.Combine("assets", fileName["assets.".Length..]);
            }
            using var input = assembly.GetManifestResourceStream(resourceName)
                ?? throw new InvalidOperationException($"Missing resource: {resourceName}");
            using var output = File.Create(Path.Combine(installDir, fileName));
            input.CopyTo(output);
        }
    }

    private static string? FindExecutable(string name)
    {
        var path = Environment.GetEnvironmentVariable("PATH");
        if (string.IsNullOrWhiteSpace(path))
        {
            return null;
        }

        foreach (var part in path.Split(Path.PathSeparator))
        {
            try
            {
                var candidate = Path.Combine(part.Trim(), name);
                if (File.Exists(candidate))
                {
                    return candidate;
                }
            }
            catch
            {
                // Ignore invalid PATH entries.
            }
        }

        return null;
    }

    private static void CreateShortcut(string shortcutPath, string targetPath, string arguments, string workingDirectory)
    {
        var shellType = Type.GetTypeFromProgID("WScript.Shell")
            ?? throw new InvalidOperationException("WScript.Shell is not available.");
        dynamic shell = Activator.CreateInstance(shellType)
            ?? throw new InvalidOperationException("Could not create WScript.Shell.");
        dynamic shortcut = shell.CreateShortcut(shortcutPath);
        shortcut.TargetPath = targetPath;
        shortcut.Arguments = arguments;
        shortcut.WorkingDirectory = workingDirectory;
        shortcut.Description = "ADAM background capture assistant";
        shortcut.Save();

        Marshal.FinalReleaseComObject(shortcut);
        Marshal.FinalReleaseComObject(shell);
    }

    private static void WriteUninstaller(string installDir, string desktop, string startMenuDir)
    {
        var uninstallPath = Path.Combine(installDir, "uninstall.ps1");
        var desktopShortcut = Path.Combine(desktop, "ADAM Capture.lnk");
        var startShortcut = Path.Combine(startMenuDir, "ADAM Capture.lnk");
        var script = $$"""
        $ErrorActionPreference = "SilentlyContinue"
        Remove-Item -LiteralPath "{{desktopShortcut}}" -Force
        Remove-Item -LiteralPath "{{startShortcut}}" -Force
        Remove-Item -LiteralPath "{{installDir}}" -Recurse -Force
        """;
        File.WriteAllText(uninstallPath, script);
    }
}
