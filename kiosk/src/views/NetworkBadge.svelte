<script lang="ts">
  type Network = {
    mode?: string;
    hat_present?: boolean;
    cellular_signal_percent?: number;
  };
  let { network }: { network?: Network } = $props();

  const labelMap: Record<string, string> = {
    cellular_router: '4G LTE',
    ethernet_client: 'Ethernet',
    unknown: 'Ühenduseta',
  };
</script>

{#if network}
  <span class="inline-flex items-center gap-1.5 rounded-md border border-slate-700 bg-slate-900/60 px-2 py-1 font-mono">
    <span class="size-1.5 rounded-full {network.mode === 'unknown' ? 'bg-red-500' : 'bg-emerald-500'}"></span>
    {labelMap[network.mode ?? 'unknown'] ?? 'Võrk'}
    {#if network.cellular_signal_percent !== undefined}
      <span class="text-slate-500">{network.cellular_signal_percent}%</span>
    {/if}
  </span>
{/if}
