package com.healthcare.referral.dto.response;

import lombok.Data;
import lombok.Builder;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;

import java.util.List;
import java.util.Map;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class DashboardStatsResponse {

    private Long totalActive;
    private Long totalCompleted;
    private Long totalCancelled;
    private Long awaitingMatch;
    private Long awaitingPriorAuth;
    private Long awaitingAppointment;
    private Long completedToday;

    private Double completionRate;
    private Double averageDaysToComplete;
    private Long leakageCount;

    private Map<String, Long> statusBreakdown;
    private Map<String, Long> specialtyBreakdown;
    private List<TrendPoint> dailyTrend;

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class TrendPoint {
        private String date;
        private Long total;
        private Long completed;
        private Long failed;
    }
}