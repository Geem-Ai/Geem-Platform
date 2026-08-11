import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cn } from '@/lib/utils';

interface MessageRendererProps {
  content: string;
  className?: string;
}

export function MessageRenderer({ content, className }: MessageRendererProps) {
  return (
    <div
      className={cn(
        'prose prose-sm dark:prose-invert max-w-none',
        '[&_pre]:overflow-x-auto [&_code]:text-xs',
        '[&_table]:block [&_table]:overflow-x-auto',
        '[&_a]:break-words',
        className,
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}
