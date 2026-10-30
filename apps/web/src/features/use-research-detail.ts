import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { endpoints, type Detail } from '../lib/api';

export function detailPollInterval(detail: Detail | undefined) {
  if (!detail) return 3000;
  const active = ['queued', 'running'].includes(detail.run.status)
    || detail.actions.some((action) => ['pending', 'running', 'unknown'].includes(action.status))
    || detail.gmail_drafts.some((draft) => ['pending', 'running', 'unknown'].includes(draft.status));
  return active ? 3000 : 30000;
}

export function useResearchDetail(id: string) {
  const client = useQueryClient();
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ['run', id] });
    void client.invalidateQueries({ queryKey: ['runs'] });
    void client.invalidateQueries({ queryKey: ['sent-review'] });
    void client.invalidateQueries({ queryKey: ['knowledge'] });
  };
  const query = useQuery({
    queryKey: ['run', id],
    queryFn: ({ signal }) => endpoints.run(id, signal),
    refetchInterval: (query) => detailPollInterval(query.state.data),
  });
  const confirm = useMutation({
    mutationFn: (identity: { company_name: string; domain: string }) => {
      if (!query.data) throw new Error('Research has not loaded');
      return endpoints.confirmIdentity(id, { version: query.data.run.version, ...identity });
    },
    onSuccess: refresh,
  });
  const decision = useMutation({
    mutationFn: ({ approvalId, approve }: { approvalId: string; approve: boolean }) => endpoints.decide(approvalId, approve),
    onSuccess: refresh,
  });
  const exportDraft = useMutation({
    mutationFn: () => {
      const report = query.data?.reports[0];
      if (!report) throw new Error('Report has not loaded');
      return endpoints.exportDraft(id, report.version);
    },
    onSuccess: refresh,
  });
  return { query, refresh, confirm, decision, exportDraft };
}
