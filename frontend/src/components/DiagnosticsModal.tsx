import React, { useEffect } from "react";
import { useStore } from "../store";
import { DiagnosticRequiredFile } from "../types";
import { GhostButton, SectionTitle } from "./ui";
import { IconBolt, IconX } from "./icons";

function Badge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center px-1.5 py-[2px] rounded-sm border text-nano font-bold tracking-[0.14em] uppercase ${
        ok
          ? "border-neon/50 bg-neon/10 text-neon"
          : "border-danger/60 bg-danger/10 text-danger"
      }`}
    >
      {label}
    </span>
  );
}

function MissingFiles({ files }: { files: DiagnosticRequiredFile[] }) {
  const missing = files.filter((it) => !it.present);
  if (!missing.length) {
    return <div className="text-nano text-neon/90">全部必需文件已在本机扫描到。</div>;
  }
  return (
    <div className="space-y-1.5">
      {missing.map((it) => (
        <a
          key={it.key}
          href={it.url}
          target="_blank"
          rel="noreferrer"
          className="block border border-line bg-ink/60 rounded-sm px-2 py-1.5 hover:border-amber/60"
          title={it.url}
        >
          <div className="text-nano text-amber font-bold truncate">{it.name}</div>
          <div className="text-[10px] text-dim truncate">{it.repo}/{it.filename}</div>
        </a>
      ))}
    </div>
  );
}

function PresentSummary({ files }: { files: DiagnosticRequiredFile[] }) {
  const present = files.filter((it) => it.present);
  if (!present.length) return null;
  const totalBytes = present.reduce((sum, it) => sum + (it.bytes || 0), 0);
  const gb = totalBytes / 1024 / 1024 / 1024;
  return (
    <div className="text-nano text-dim tabular-nums">
      present {present.length}/{files.length} · {gb.toFixed(gb >= 10 ? 1 : 2)} GB scanned
    </div>
  );
}

function gb(bytes?: number) {
  if (!bytes) return "0.0 GB";
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

export default function DiagnosticsModal() {
  const show = useStore((s) => s.showDiagnostics);
  const set = useStore((s) => s.set);
  const report = useStore((s) => s.diagnostics);
  const loading = useStore((s) => s.diagnosticsLoading);
  const refresh = useStore((s) => s.refreshDiagnostics);

  useEffect(() => {
    if (show) refresh();
  }, [show, refresh]);

  if (!show) return null;
  const close = () => set({ showDiagnostics: false });

  const depsMissing = report?.dependencies.items.filter((it) => !it.ok) || [];
  const deviceOk = !!report?.device.ready;
  const runnerOk = !!report?.runner_entrypoint.ok;
  const dryRunOk = !!report?.dry_run.ok;
  const integrityOk = !!report?.model_integrity.ok || !!report?.model_integrity.skipped;
  const integrityFailed = report?.model_integrity.items.filter((it) => !it.ok) || [];
  const bundleOk = !!report?.component_bundle?.ok || !!report?.component_bundle?.skipped;
  const bundleErrors = report?.component_bundle?.errors || [];

  return (
    <div className="fixed inset-0 z-50 bg-ink/80 backdrop-blur-sm flex items-center justify-center p-6" onClick={close}>
      <div
        className="w-[960px] max-w-full max-h-[88vh] bg-panel border border-line2 rounded-sm flex flex-col shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-line">
          <span className="inline-flex items-center gap-2 text-micro font-bold tracking-[0.2em] text-lit uppercase">
            <IconBolt size={12} /> Local Diagnostics / 本地诊断
          </span>
          <button type="button" onClick={close} className="text-dim hover:text-lit p-1">
            <IconX />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {loading && !report && <div className="text-micro text-dim">正在读取本机依赖和模型状态…</div>}

          {report && (
            <>
              <div className="grid grid-cols-6 gap-2">
                <div className="border border-line bg-ink/60 rounded-sm p-2 space-y-1">
                  <div className="text-nano text-dim uppercase tracking-[0.16em]">overall</div>
                  <Badge ok={report.overall_ready} label={report.overall_ready ? "ready" : "not ready"} />
                </div>
                <div className="border border-line bg-ink/60 rounded-sm p-2 space-y-1">
                  <div className="text-nano text-dim uppercase tracking-[0.16em]">dependencies</div>
                  <Badge ok={report.dependencies.ready} label={report.dependencies.ready ? "ok" : "missing"} />
                </div>
                <div className="border border-line bg-ink/60 rounded-sm p-2 space-y-1">
                  <div className="text-nano text-dim uppercase tracking-[0.16em]">gpu</div>
                  <Badge ok={deviceOk} label={deviceOk ? "ready" : "blocked"} />
                </div>
                <div className="border border-line bg-ink/60 rounded-sm p-2 space-y-1">
                  <div className="text-nano text-dim uppercase tracking-[0.16em]">render models</div>
                  <Badge ok={report.render_models.ready} label={report.render_models.ready ? "ok" : "missing"} />
                </div>
                <div className="border border-line bg-ink/60 rounded-sm p-2 space-y-1">
                  <div className="text-nano text-dim uppercase tracking-[0.16em]">prompt llm</div>
                  <Badge ok={report.llm_models.ready} label={report.llm_models.ready ? "ok" : "missing"} />
                </div>
                <div className="border border-line bg-ink/60 rounded-sm p-2 space-y-1">
                  <div className="text-nano text-dim uppercase tracking-[0.16em]">runner</div>
                  <Badge ok={runnerOk && dryRunOk && integrityOk && bundleOk} label={runnerOk && dryRunOk && integrityOk && bundleOk ? "ok" : "blocked"} />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <SectionTitle label="Runtime / 运行依赖" hint={report.python.platform} />
                  <div className="border border-line bg-ink/60 rounded-sm p-2 space-y-1.5">
                    <div className="text-[10px] text-dim break-all">Python: {report.python.executable}</div>
                    {depsMissing.length ? (
                      depsMissing.map((it) => (
                        <div key={it.module} className="text-nano text-danger leading-4">
                          {it.package} ({it.module}) · {it.error}
                        </div>
                      ))
                    ) : (
                      <div className="text-nano text-neon/90">LTX Python 依赖全部可导入。</div>
                    )}
                  </div>
                </div>

                <div className="space-y-2">
                  <SectionTitle label="Device / GPU" hint={report.device.torch_cuda_version || "CUDA"} />
                  <div className="border border-line bg-ink/60 rounded-sm p-2 space-y-1.5">
                    <div className={deviceOk ? "text-nano text-neon/90" : "text-nano text-danger"}>
                      {report.device.detail || (deviceOk ? "CUDA ready" : "CUDA not available")}
                    </div>
                    <div className="text-[10px] text-dim break-all">
                      torch {report.device.torch_version || "unavailable"} · cuda build {report.device.torch_cuda_version || "none"}
                    </div>
                    {report.device.devices.map((it) => (
                      <div key={it.index} className="text-nano text-lit leading-4">
                        GPU {it.index}: {it.name} · cc {it.capability} · {gb(it.free_memory ?? it.total_memory)} / {gb(it.total_memory)}
                      </div>
                    ))}
                    {!report.device.devices.length && report.device.nvidia_smi.summary.map((line) => (
                      <div key={line} className="text-nano text-dim leading-4">{line}</div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <SectionTitle label="Runner / 渲染入口" hint="backend.ltx_runner" />
                  <div className="border border-line bg-ink/60 rounded-sm p-2 space-y-1.5">
                    <div className={runnerOk ? "text-nano text-neon/90" : "text-nano text-danger"}>
                      entrypoint: {runnerOk ? "OK" : report.runner_entrypoint.error || `return ${report.runner_entrypoint.returncode}`}
                    </div>
                    <div className={dryRunOk ? "text-nano text-neon/90" : "text-nano text-amber"}>
                      dry-run command: {dryRunOk ? "OK" : report.dry_run.reason || report.dry_run.error || "not ready"}
                    </div>
                    {report.dry_run.command && (
                      <div className="text-[10px] text-dim break-all max-h-20 overflow-y-auto">
                        {report.dry_run.command.join(" ")}
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <SectionTitle label="Safetensors / 文件完整性" hint="metadata + tensor index" />
                <div className="border border-line bg-ink/60 rounded-sm p-2 space-y-1.5">
                  {report.model_integrity.skipped ? (
                    <div className="text-nano text-amber">
                      skipped · {report.model_integrity.reason || "runtime or models are not ready"}
                    </div>
                  ) : integrityFailed.length ? (
                    integrityFailed.map((it) => (
                      <div key={it.key} className="text-nano text-danger leading-4">
                        {it.name} · {it.error || "invalid safetensors file"}
                      </div>
                    ))
                  ) : (
                    <div className="text-nano text-neon/90">
                      safetensors 文件可打开，必需 metadata config 已通过预检。
                    </div>
                  )}
                </div>
              </div>

              <div className="space-y-2">
                <SectionTitle label="Component Bundle / 组件组合" hint="official loader preflight" />
                <div className="border border-line bg-ink/60 rounded-sm p-2 space-y-1.5">
                  {report.component_bundle?.skipped ? (
                    <div className="text-nano text-amber">
                      skipped · {report.component_bundle.reason || "runtime or models are not ready"}
                    </div>
                  ) : bundleErrors.length ? (
                    bundleErrors.map((err) => (
                      <div key={err} className="text-nano text-danger leading-4">
                        {err}
                      </div>
                    ))
                  ) : (
                    <div className="text-nano text-neon/90">
                      当前默认组件组合包含 transformer、Video VAE、Audio VAE、vocoder、text projection 与 upscaler 配置。
                    </div>
                  )}
                  {!!report.component_bundle?.config_keys?.length && (
                    <div className="text-[10px] text-dim break-all">
                      config: {report.component_bundle.config_keys.join(", ")}
                    </div>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <SectionTitle label="Render Models / 渲染模型" hint={report.paths.ltx_model_dir} />
                  <PresentSummary files={report.render_models.required} />
                  <MissingFiles files={report.render_models.required} />
                </div>
                <div className="space-y-2">
                  <SectionTitle label="Prompt LLM / 提示词模型" hint={report.paths.llm_model_dir} />
                  <PresentSummary files={report.llm_models.required} />
                  <MissingFiles files={report.llm_models.required} />
                </div>
              </div>
            </>
          )}
        </div>

        <div className="px-4 py-3 border-t border-line flex items-center justify-between">
          <span className="text-nano text-dim/80">
            诊断只读取本机状态；安装和下载请运行 Linux 脚本。
          </span>
          <div className="flex gap-2">
            <GhostButton onClick={refresh} disabled={loading}>{loading ? "refreshing…" : "refresh"}</GhostButton>
            <GhostButton onClick={close}>close</GhostButton>
          </div>
        </div>
      </div>
    </div>
  );
}
