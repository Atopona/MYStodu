import React, { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useStore } from "../store";
import { Settings } from "../types";
import { GhostButton, SectionTitle, Select } from "./ui";
import { IconX } from "./icons";

function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between">
        <span className="text-nano font-bold tracking-[0.16em] uppercase text-fog">{label}</span>
        {hint && <span className="text-nano text-dim/70">{hint}</span>}
      </div>
      {children}
    </div>
  );
}

const inputCls =
  "w-full bg-panel2 border border-line rounded-sm px-2 py-[6px] text-tiny text-lit outline-none focus:border-line2";

export default function SettingsModal() {
  const show = useStore((s) => s.showSettings);
  const set = useStore((s) => s.set);
  const toast = useStore((s) => s.toast);
  const llm = useStore((s) => s.llm);
  const storeSettings = useStore((s) => s.settings);
  const [form, setForm] = useState<Settings | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (show) {
      api
        .getSettings()
        .then((s) => setForm(s))
        .catch((e) => toast(e.message, "err"));
    }
  }, [show, toast]);

  if (!show) return null;
  const close = () => set({ showSettings: false });

  const f = form || (storeSettings as Settings | null);
  if (!f) {
    return (
      <div className="fixed inset-0 z-50 bg-ink/80 flex items-center justify-center">
        <div className="text-micro text-dim">loading settings…</div>
      </div>
    );
  }

  const up = (patch: Partial<Settings>) => setForm({ ...f, ...patch });

  const save = async () => {
    setBusy(true);
    try {
      const saved = await api.saveSettings(f);
      set({ settings: saved });
      toast("设置已保存", "ok");
      close();
    } catch (e: any) {
      toast(`保存失败：${e.message}`, "err");
    } finally {
      setBusy(false);
    }
  };

  const startLlm = async () => {
    setBusy(true);
    try {
      await api.saveSettings(f);
      set({ settings: f });
      toast(
        f.llm_mode === "embedded"
          ? "正在加载内置本地 LLM 引擎（模型加载可能需要数十秒）…"
          : "正在启动兼容 LLM 子进程（模型加载可能需要数十秒）…",
        "warn"
      );
      await api.llmStart();
      toast("本地 LLM 已就绪", "ok");
    } catch (e: any) {
      toast(e.message, "err");
    } finally {
      setBusy(false);
    }
  };

  const stopLlm = async () => {
    try {
      await api.llmStop();
      toast("本地 LLM 已停止", "ok");
    } catch (e: any) {
      toast(e.message, "err");
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-ink/80 backdrop-blur-sm flex items-center justify-center p-6" onClick={close}>
      <div
        className="w-[760px] max-w-full max-h-[88vh] bg-panel border border-line2 rounded-sm flex flex-col shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-line">
          <span className="text-micro font-bold tracking-[0.2em] text-lit uppercase">Settings / 设置</span>
          <button type="button" onClick={close} className="text-dim hover:text-lit p-1">
            <IconX />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 grid grid-cols-2 gap-x-5 gap-y-3.5">
          {/* ---- ComfyUI ---- */}
          <div className="col-span-2">
            <SectionTitle label="ComfyUI / 可选真实渲染" hint="不安装也可用 Mock 完整演示" />
          </div>
          <Field label="ComfyUI URL / 地址">
            <input className={inputCls} value={f.comfy_url} onChange={(e) => up({ comfy_url: e.target.value })} />
          </Field>
          <Field label="Mock ComfyUI / 离线渲染" hint="auto = 不可达时自动模拟">
            <Select
              value={f.mock_comfy}
              onChange={(v) => up({ mock_comfy: v as Settings["mock_comfy"] })}
              options={["auto", "on", "off"]}
            />
          </Field>
          <Field label="Render timestamps / 渲染时间戳" hint="默认剥离 [0-12s]">
            <Select
              value={f.keep_timestamps ? "keep" : "strip"}
              onChange={(v) => up({ keep_timestamps: v === "keep" })}
              options={["strip", "keep"]}
            />
          </Field>
          <Field label="Negative prompt / 负面提示词">
            <input
              className={inputCls}
              value={f.negative_prompt}
              onChange={(e) => up({ negative_prompt: e.target.value })}
            />
          </Field>

          {/* ---- LLM ---- */}
          <div className="col-span-2 pt-1">
            <SectionTitle
              label="LLM / 本地提示词引擎"
              hint={`状态: ${llm.state}${llm.detail ? " · " + llm.detail : ""}`}
            />
          </div>
          <Field label="Mode / 模式" hint="embedded = 后端进程内加载，不开独立 LLM 服务">
            <Select
              value={f.llm_mode}
              onChange={(v) => up({ llm_mode: v as Settings["llm_mode"] })}
              options={["embedded", "managed"]}
            />
          </Field>
          <Field label="Mock LLM / 离线提示词" hint="auto = 未加载模型时自动模拟">
            <Select
              value={f.mock_llm}
              onChange={(v) => up({ mock_llm: v as Settings["mock_llm"] })}
              options={["auto", "on", "off"]}
            />
          </Field>

          {f.llm_mode === "embedded" ? (
            <>
              <div className="col-span-2 border border-acid/40 bg-acid/10 rounded-sm p-2 text-nano leading-4 text-acid">
                内置模式会在 FastAPI 后端进程内直接加载 GGUF，不需要另开 llama-server、LM Studio 或 Ollama。
              </div>
              <Field label="GGUF model / 主模型" hint="models/llm 下文件名或绝对路径">
                <input className={inputCls} value={f.llm_gguf} onChange={(e) => up({ llm_gguf: e.target.value })} />
              </Field>
              <Field label="mmproj / 视觉投影" hint="多模态图像分析文件">
                <input className={inputCls} value={f.llm_mmproj} onChange={(e) => up({ llm_mmproj: e.target.value })} />
              </Field>
              <Field label="-ngl GPU layers / GPU 层数">
                <input
                  className={inputCls}
                  value={String(f.llm_ngl)}
                  onChange={(e) => up({ llm_ngl: Number(e.target.value.replace(/\D/g, "")) || 0 })}
                />
              </Field>
              <Field label="-c context / 上下文长度">
                <input
                  className={inputCls}
                  value={String(f.llm_ctx)}
                  onChange={(e) => up({ llm_ctx: Number(e.target.value.replace(/\D/g, "")) || 8192 })}
                />
              </Field>
              <Field label="Autostart / 启动时加载">
                <Select
                  value={f.auto_start_llm ? "yes" : "no"}
                  onChange={(v) => up({ auto_start_llm: v === "yes" })}
                  options={["no", "yes"]}
                />
              </Field>
            </>
          ) : f.llm_mode === "managed" ? (
            <>
              <div className="col-span-2 border border-amber/50 bg-amber/10 rounded-sm p-2 text-nano leading-4 text-amber">
                兼容模式会由后端托管一个项目内 llama-server 子进程；推荐 Linux 使用 embedded 内置模式。
              </div>
              <Field label="llama-server path / 兼容子进程路径" hint="setup 脚本可下载">
                <input
                  className={inputCls}
                  value={f.llama_server_path}
                  onChange={(e) => up({ llama_server_path: e.target.value })}
                  placeholder="tools\\llama.cpp\\llama-server.exe"
                />
              </Field>
              <Field label="Port / 端口">
                <input
                  className={inputCls}
                  value={String(f.llm_port)}
                  onChange={(e) => up({ llm_port: Number(e.target.value.replace(/\D/g, "")) || 8731 })}
                />
              </Field>
              <Field label="GGUF model / 主模型" hint="models/llm 下文件名或绝对路径">
                <input className={inputCls} value={f.llm_gguf} onChange={(e) => up({ llm_gguf: e.target.value })} />
              </Field>
              <Field label="mmproj / 视觉投影" hint="多模态投影文件">
                <input className={inputCls} value={f.llm_mmproj} onChange={(e) => up({ llm_mmproj: e.target.value })} />
              </Field>
              <Field label="-ngl GPU layers / GPU 层数">
                <input
                  className={inputCls}
                  value={String(f.llm_ngl)}
                  onChange={(e) => up({ llm_ngl: Number(e.target.value.replace(/\D/g, "")) || 0 })}
                />
              </Field>
              <Field label="-c context / 上下文长度">
                <input
                  className={inputCls}
                  value={String(f.llm_ctx)}
                  onChange={(e) => up({ llm_ctx: Number(e.target.value.replace(/\D/g, "")) || 8192 })}
                />
              </Field>
              <Field label="Extra args / 额外参数">
                <input
                  className={inputCls}
                  value={f.llm_extra_args}
                  onChange={(e) => up({ llm_extra_args: e.target.value })}
                  placeholder="--flash-attn …"
                />
              </Field>
              <Field label="Autostart / 启动时加载">
                <Select
                  value={f.auto_start_llm ? "yes" : "no"}
                  onChange={(v) => up({ auto_start_llm: v === "yes" })}
                  options={["no", "yes"]}
                />
              </Field>
            </>
          ) : (
            <>
              <div className="col-span-2 border border-danger/50 bg-danger/10 rounded-sm p-2 text-nano leading-4 text-danger">
                外部端点模式已不推荐，只保留给调试旧配置；正常使用请选择 embedded。
              </div>
              <Field label="External OpenAI-compatible URL / 外部端点" hint="不推荐">
                <input
                  className={inputCls}
                  value={f.external_llm_url}
                  onChange={(e) => up({ external_llm_url: e.target.value })}
                  placeholder="http://127.0.0.1:8080"
                />
              </Field>
              <Field label="API key / 密钥（可选）">
                <input
                  className={inputCls}
                  value={f.llm_api_key}
                  onChange={(e) => up({ llm_api_key: e.target.value })}
                />
              </Field>
            </>
          )}

          <Field label="Prompt style / 提示词风格" hint="sulphur = 无 system prompt 直发">
            <Select
              value={f.prompt_style}
              onChange={(v) => up({ prompt_style: v as Settings["prompt_style"] })}
              options={["auto", "sulphur", "director"]}
            />
          </Field>

          <div className="flex items-end gap-1.5">
            {(f.llm_mode === "embedded" || f.llm_mode === "managed") && (
              <>
                <GhostButton onClick={startLlm} disabled={busy} className="flex-1 !py-[7px] text-acid">
                  {llm.state === "starting" || llm.state === "loading" ? "loading…" : "load / restart llm"}
                </GhostButton>
                <GhostButton onClick={stopLlm} disabled={busy} className="!py-[7px]">
                  stop
                </GhostButton>
              </>
            )}
          </div>

          {llm.tail && llm.tail.length > 0 && (
            <div className="col-span-2 border border-line bg-ink/60 rounded-sm p-2 max-h-28 overflow-y-auto">
              {llm.tail.map((t, i) => (
                <div key={i} className="text-[9px] leading-[13px] text-dim break-all">
                  {t}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="px-4 py-3 border-t border-line flex justify-between items-center">
          <span className="text-nano text-dim/70">
            提示：Linux 运行 install_linux.sh 可安装内置 LLM 依赖并下载模型；ComfyUI 不安装也能用 Mock。
          </span>
          <div className="flex gap-2">
            <GhostButton onClick={close}>取消</GhostButton>
            <button
              type="button"
              disabled={busy}
              onClick={save}
              className="px-4 py-[5px] rounded-sm bg-gradient-to-r from-acid to-neon text-ink text-nano font-extrabold tracking-[0.2em] uppercase hover:brightness-110 disabled:opacity-50"
            >
              保存设置
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
