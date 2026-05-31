using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text;
using System.Threading;
using System.Windows.Forms;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length < 3)
        {
            MessageBox.Show("Usage: ExtractWithProgress.exe <archive> <destination> <title>", "ANTHOLOGY", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 2;
        }

        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        using (var form = new ExtractForm(args[0], args[1], args[2]))
        {
            Application.Run(form);
            return form.ExitCode;
        }
    }
}

internal sealed class ExtractForm : Form
{
    private readonly string archivePath;
    private readonly string destinationPath;
    private readonly Label titleLabel;
    private readonly Label archiveLabel;
    private readonly ProgressBar progressBar;
    private readonly Label progressLabel;
    private readonly Label noteLabel;
    private readonly System.Windows.Forms.Timer progressTimer;
    private readonly DateTime startedAt;

    private long totalArchiveBytes;
    private long baselineBytes;
    private string trackedPath;
    private volatile bool extractionFinished;
    private int exitCode = 1;

    public int ExitCode { get { return exitCode; } }

    public ExtractForm(string archivePath, string destinationPath, string titleText)
    {
        this.archivePath = archivePath;
        this.destinationPath = destinationPath;

        Text = "ANTHOLOGY";
        ClientSize = new Size(560, 190);
        StartPosition = FormStartPosition.CenterScreen;
        TopMost = true;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;
        ControlBox = false;
        Font = new Font("Segoe UI", 9F);

        titleLabel = new Label();
        titleLabel.Left = 20;
        titleLabel.Top = 18;
        titleLabel.Width = 520;
        titleLabel.Height = 24;
        titleLabel.Font = new Font(Font, FontStyle.Bold);
        titleLabel.Text = titleText;
        Controls.Add(titleLabel);

        archiveLabel = new Label();
        archiveLabel.Left = 20;
        archiveLabel.Top = 50;
        archiveLabel.Width = 520;
        archiveLabel.Height = 22;
        archiveLabel.Text = Path.GetFileName(archivePath);
        Controls.Add(archiveLabel);

        progressBar = new ProgressBar();
        progressBar.Left = 20;
        progressBar.Top = 82;
        progressBar.Width = 520;
        progressBar.Height = 24;
        progressBar.Style = ProgressBarStyle.Marquee;
        progressBar.MarqueeAnimationSpeed = 18;
        Controls.Add(progressBar);

        progressLabel = new Label();
        progressLabel.Left = 20;
        progressLabel.Top = 114;
        progressLabel.Width = 520;
        progressLabel.Height = 22;
        progressLabel.Text = "Идет подготовка расчета прогресса...";
        Controls.Add(progressLabel);

        noteLabel = new Label();
        noteLabel.Left = 20;
        noteLabel.Top = 145;
        noteLabel.Width = 520;
        noteLabel.Height = 36;
        noteLabel.Text = "Пожалуйста, дождитесь завершения. Отмена распаковки отключена.";
        Controls.Add(noteLabel);

        startedAt = DateTime.Now;
        progressTimer = new System.Windows.Forms.Timer();
        progressTimer.Interval = 3000;
        progressTimer.Tick += delegate { UpdateMeasuredProgress(DateTime.Now - startedAt); };
        progressTimer.Start();

        Shown += delegate
        {
            Activate();
            BringToFront();
            StartExtraction();
        };

        FormClosing += delegate(object sender, FormClosingEventArgs e)
        {
            if (!extractionFinished)
                e.Cancel = true;
        };
    }

    private void StartExtraction()
    {
        var worker = new Thread(RunExtraction);
        worker.IsBackground = true;
        worker.Start();
    }

    private void RunExtraction()
    {
        try
        {
            string exeDir = Path.GetDirectoryName(Application.ExecutablePath);
            string sevenZip = Path.Combine(exeDir, "7z.exe");
            if (!File.Exists(sevenZip))
                throw new FileNotFoundException("7z.exe not found", sevenZip);

            PrepareMeasuredProgress(sevenZip);

            var psi = new ProcessStartInfo();
            psi.FileName = sevenZip;
            psi.Arguments = "x " + Quote(archivePath) + " -o" + Quote(destinationPath) + " -y -bsp1 -bso0 -bse1";
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;
            psi.StandardOutputEncoding = Encoding.Default;
            psi.StandardErrorEncoding = Encoding.Default;

            using (var process = Process.Start(psi))
            {
                var stdout = new Thread(new ThreadStart(delegate { Drain(process.StandardOutput); }));
                var stderr = new Thread(new ThreadStart(delegate { Drain(process.StandardError); }));
                stdout.IsBackground = true;
                stderr.IsBackground = true;
                stdout.Start();
                stderr.Start();

                process.WaitForExit();
                stdout.Join(1000);
                stderr.Join(1000);
                exitCode = process.ExitCode;
            }

            if (exitCode == 0)
            {
                SetProgressDone();
                SetNote("Готово.");
                Thread.Sleep(700);
            }
            else
            {
                ShowError("7-Zip вернул ошибку: " + exitCode);
            }
        }
        catch (Exception ex)
        {
            exitCode = 1;
            ShowError(ex.Message);
        }
        finally
        {
            extractionFinished = true;
            BeginInvoke(new MethodInvoker(Close));
        }
    }

    private void PrepareMeasuredProgress(string sevenZip)
    {
        ArchiveInfo info = AnalyzeArchive(sevenZip);
        if (info.TotalBytes <= 0)
            return;

        trackedPath = destinationPath;
        if (!string.IsNullOrEmpty(info.RootName))
            trackedPath = Path.Combine(destinationPath, info.RootName);

        totalArchiveBytes = info.TotalBytes;
        baselineBytes = GetDirectorySize(trackedPath);

        BeginInvoke(new MethodInvoker(delegate
        {
            progressBar.Style = ProgressBarStyle.Continuous;
            progressBar.Minimum = 0;
            progressBar.Maximum = 100;
            progressBar.Value = 0;
            progressLabel.Text = "0%";
        }));
    }

    private ArchiveInfo AnalyzeArchive(string sevenZip)
    {
        var psi = new ProcessStartInfo();
        psi.FileName = sevenZip;
        psi.Arguments = "l -slt " + Quote(archivePath);
        psi.UseShellExecute = false;
        psi.CreateNoWindow = true;
        psi.RedirectStandardOutput = true;
        psi.RedirectStandardError = true;
        psi.StandardOutputEncoding = Encoding.Default;
        psi.StandardErrorEncoding = Encoding.Default;

        using (var process = Process.Start(psi))
        {
            string output = process.StandardOutput.ReadToEnd();
            process.StandardError.ReadToEnd();
            process.WaitForExit();
            if (process.ExitCode != 0)
                return new ArchiveInfo();

            return ParseArchiveList(output);
        }
    }

    private static ArchiveInfo ParseArchiveList(string output)
    {
        var info = new ArchiveInfo();
        bool inEntries = false;
        string currentPath = null;
        string currentAttributes = "";
        long currentSize = 0;

        Action flush = delegate
        {
            if (currentPath == null)
                return;

            string normalized = currentPath.Replace('/', '\\').Trim('\\');
            if (info.RootName == null && normalized.Length > 0)
            {
                int slash = normalized.IndexOf('\\');
                info.RootName = slash >= 0 ? normalized.Substring(0, slash) : normalized;
            }

            if (currentAttributes.IndexOf('D') < 0)
                info.TotalBytes += currentSize;

            currentPath = null;
            currentAttributes = "";
            currentSize = 0;
        };

        string[] lines = output.Replace("\r\n", "\n").Split('\n');
        foreach (string rawLine in lines)
        {
            string line = rawLine.TrimEnd('\r');
            if (line == "----------")
            {
                inEntries = true;
                continue;
            }

            if (!inEntries)
                continue;

            if (line.Length == 0)
            {
                flush();
                continue;
            }

            if (line.StartsWith("Path = "))
                currentPath = line.Substring(7);
            else if (line.StartsWith("Size = "))
            {
                long parsed;
                if (long.TryParse(line.Substring(7).Trim(), out parsed))
                    currentSize = parsed;
            }
            else if (line.StartsWith("Attributes = "))
                currentAttributes = line.Substring(13);
        }

        flush();
        return info;
    }

    private void UpdateMeasuredProgress(TimeSpan elapsed)
    {
        if (totalArchiveBytes <= 0 || string.IsNullOrEmpty(trackedPath))
        {
            progressLabel.Text = "Идет распаковка... прошло " + elapsed.ToString(@"hh\:mm\:ss");
            return;
        }

        long currentBytes = GetDirectorySize(trackedPath) - baselineBytes;
        if (currentBytes < 0)
            currentBytes = 0;

        int percent = (int)Math.Min(99, (currentBytes * 100L) / totalArchiveBytes);
        if (percent < 0)
            percent = 0;

        progressBar.Value = percent;
        progressLabel.Text = percent + "%, прошло " + elapsed.ToString(@"hh\:mm\:ss");
    }

    private void SetProgressDone()
    {
        BeginInvoke(new MethodInvoker(delegate
        {
            progressTimer.Stop();
            progressBar.Style = ProgressBarStyle.Continuous;
            progressBar.Minimum = 0;
            progressBar.Maximum = 100;
            progressBar.Value = 100;
            progressLabel.Text = "100%";
        }));
    }

    private void SetNote(string text)
    {
        BeginInvoke(new MethodInvoker(delegate { noteLabel.Text = text; }));
    }

    private void ShowError(string text)
    {
        BeginInvoke(new MethodInvoker(delegate
        {
            MessageBox.Show(this, text, "ANTHOLOGY", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }));
    }

    private static void Drain(StreamReader reader)
    {
        while (reader.Read() >= 0) { }
    }

    private static long GetDirectorySize(string path)
    {
        if (!Directory.Exists(path))
            return 0;

        long size = 0;
        try
        {
            foreach (string file in Directory.GetFiles(path, "*", SearchOption.AllDirectories))
            {
                try
                {
                    size += new FileInfo(file).Length;
                }
                catch
                {
                }
            }
        }
        catch
        {
        }

        return size;
    }

    private static string Quote(string value)
    {
        if (value.Length == 0)
            return "\"\"";

        var result = new StringBuilder();
        result.Append('"');
        int backslashes = 0;
        for (int i = 0; i < value.Length; i++)
        {
            char c = value[i];
            if (c == '\\')
            {
                backslashes++;
            }
            else if (c == '"')
            {
                result.Append('\\', backslashes * 2 + 1);
                result.Append('"');
                backslashes = 0;
            }
            else
            {
                result.Append('\\', backslashes);
                backslashes = 0;
                result.Append(c);
            }
        }

        result.Append('\\', backslashes * 2);
        result.Append('"');
        return result.ToString();
    }

    private sealed class ArchiveInfo
    {
        public long TotalBytes;
        public string RootName;
    }
}
