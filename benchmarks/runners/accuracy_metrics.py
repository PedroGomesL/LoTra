"""
Módulo de cálculo de métricas de acurácia de extração de texto (CER, WER, Exact Match)
e avaliação da qualidade e resiliência da tradução.
"""

def levenshtein_distance(s1, s2):
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    return dp[m][n]

def compute_cer(reference, hypothesis):
    """Character Error Rate (quanto menor, melhor; 0.0 = perfeito)."""
    ref = reference.strip()
    hyp = hypothesis.strip()
    if not ref:
        return 0.0 if not hyp else 1.0
    dist = levenshtein_distance(ref, hyp)
    return min(1.0, dist / len(ref))

def compute_wer(reference, hypothesis):
    """Word Error Rate."""
    ref_words = reference.strip().split()
    hyp_words = hypothesis.strip().split()
    if not ref_words:
        return 0.0 if not hyp_words else 1.0
    dist = levenshtein_distance(ref_words, hyp_words)
    return min(1.0, dist / len(ref_words))

def compute_accuracy(reference, hypothesis):
    """Retorna taxa de acerto em porcentagem (100% = idêntico)."""
    cer = compute_cer(reference, hypothesis)
    return max(0.0, (1.0 - cer) * 100.0)

def evaluate_translation_accuracy(generated_pt, ground_truth_pt, alternatives_pt=None):
    """
    Avalia se a tradução contém o termo correto em português brasileiro,
    considerando variações válidas e sinônimos.
    """
    gen = generated_pt.lower().strip()
    gt = ground_truth_pt.lower().strip()
    
    # 1. Correspondência exata ou contenção do termo principal
    if gt in gen:
        return 100.0, "Perfeita (termo primário identificado)"
        
    # 2. Sinônimos válidos
    if alternatives_pt:
        for alt in alternatives_pt:
            if alt.lower() in gen:
                return 95.0, f"Excelente (sinônimo contextual válido: '{alt}')"
                
    # 3. Similaridade aproximada de caracteres
    sim = max(0.0, (1.0 - compute_cer(gt, gen)) * 100.0)
    if sim >= 70.0:
        return sim, "Aceitável (pequena variação de concordância/raiz)"
        
    return 0.0, "Incorreta / Não condiz com o contexto"
