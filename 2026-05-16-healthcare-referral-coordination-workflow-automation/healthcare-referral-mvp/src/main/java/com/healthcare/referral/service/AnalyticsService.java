package com.healthcare.referral.service;

import com.healthcare.referral.domain.enums.ReferralStatus;
import com.healthcare.referral.dto.response.DashboardStatsResponse;
import com.healthcare.referral.repository.ReferralRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;

@Service
@RequiredArgsConstructor
@Slf4j
public class AnalyticsService {

    private final ReferralRepository referralRepository;

    public DashboardStatsResponse getDashboardStats() {
        // Status counts
        List<Object[]> statusCounts = referralRepository.countByStatus();
        Map<String, Long> statusMap = new LinkedHashMap<>();
        long totalActive = 0;
        long totalCompleted = 0;
        long totalCancelled = 0;

        for (Object[] row : statusCounts) {
            String status = row[0].toString();
            Long count = ((Number) row[1]).longValue();
            statusMap.put(status, count);

            if (status.equals("COMPLETED")) totalCompleted = count;
            else if (status.equals("CANCELLED") || status.equals("FAILED")) totalCancelled += count;
            else totalActive += count;
        }

        long awaitingMatch = referralRepository.countByStatus(ReferralStatus.MATCHING);
        long awaitingAuth = referralRepository.countByStatus(ReferralStatus.PRIOR_AUTH_SUBMITTED);
        long awaitingAppt = referralRepository.countByStatus(ReferralStatus.SENT_TO_SPECIALIST)
                + referralRepository.countByStatus(ReferralStatus.PATIENT_NOTIFIED);
        long completedToday = countCompletedToday();

        // Specialty breakdown
        Map<String, Long> specialtyBreakdown = getSpecialtyBreakdown();

        // Daily trend (last 7 days)
        List<DashboardStatsResponse.TrendPoint> trend = getDailyTrend();

        // Completion rate
        long total = totalActive + totalCompleted + totalCancelled;
        double completionRate = total > 0 ? (double) totalCompleted / total * 100 : 0;

        return DashboardStatsResponse.builder()
                .totalActive(totalActive)
                .totalCompleted(totalCompleted)
                .totalCancelled(totalCancelled)
                .awaitingMatch(awaitingMatch)
                .awaitingPriorAuth(awaitingAuth)
                .awaitingAppointment(awaitingAppt)
                .completedToday(completedToday)
                .completionRate(Math.round(completionRate * 10.0) / 10.0)
                .statusBreakdown(statusMap)
                .specialtyBreakdown(specialtyBreakdown)
                .dailyTrend(trend)
                .build();
    }

    private long countCompletedToday() {
        LocalDateTime startOfDay = LocalDateTime.now().withHour(0).withMinute(0).withSecond(0);
        return referralRepository.findAll().stream()
                .filter(r -> r.getStatus() == ReferralStatus.COMPLETED)
                .filter(r -> r.getCompletedAt() != null && r.getCompletedAt().isAfter(startOfDay))
                .count();
    }

    private Map<String, Long> getSpecialtyBreakdown() {
        Map<String, Long> breakdown = new LinkedHashMap<>();
        referralRepository.findAll().forEach(r -> {
            String specialty = r.getSpecialtyNeeded() != null ? r.getSpecialtyNeeded() : "Unknown";
            breakdown.merge(specialty, 1L, Long::sum);
        });
        return breakdown;
    }

    private List<DashboardStatsResponse.TrendPoint> getDailyTrend() {
        LocalDateTime sevenDaysAgo = LocalDateTime.now().minusDays(7);
        List<Object[]> rawData = referralRepository.getDailyReferralStats(sevenDaysAgo);

        List<DashboardStatsResponse.TrendPoint> trend = new ArrayList<>();
        for (Object[] row : rawData) {
            trend.add(DashboardStatsResponse.TrendPoint.builder()
                    .date(row[0].toString())
                    .total(((Number) row[1]).longValue())
                    .completed(((Number) row[2]).longValue())
                    .failed(((Number) row[3]).longValue())
                    .build());
        }
        return trend;
    }
}